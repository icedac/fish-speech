"""Benchmark script to test VoiceReel performance optimizations."""

import argparse
import json
import os
import time
from typing import Dict, List

import numpy as np
from loguru import logger

# Add parent directory to path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voicereel.config import config
from voicereel.fish_speech_integration import FishSpeechEngine
from voicereel.fish_speech_optimized import OptimizedFishSpeechEngine


def generate_test_scripts(num_segments: int = 10) -> List[Dict[str, str]]:
    """Generate test scripts for benchmarking."""
    test_texts = [
        "Hello, this is a performance test for the VoiceReel text-to-speech system.",
        "We are testing how fast we can generate high-quality speech from text.",
        "The goal is to achieve thirty seconds of audio in less than eight seconds.",
        "This benchmark will help us optimize the synthesis pipeline.",
        "Multiple speakers can be used to create dynamic conversations.",
        "Each segment is processed and then combined into a single audio file.",
        "Performance optimization includes GPU acceleration and parallel processing.",
        "The Fish-Speech engine provides natural sounding voices.",
        "We measure both the processing time and the quality of output.",
        "Let's see how well our optimizations perform in practice.",
    ]
    
    script = []
    for i in range(num_segments):
        script.append({
            "speaker_id": f"spk_{i % 2 + 1}",  # Alternate between 2 speakers
            "text": test_texts[i % len(test_texts)]
        })
    
    return script


def create_dummy_speaker_features() -> Dict[str, Dict[str, any]]:
    """Create dummy speaker features for testing."""
    # In real usage, these would be extracted from reference audio
    features = {}
    
    for i in range(1, 3):  # 2 speakers
        features[f"spk_{i}"] = {
            "vq_tokens": np.random.randint(0, 1000, (4, 100)).tolist(),
            "text_tokens": np.random.randint(0, 500, (100,)).tolist(),
            "reference_text": f"This is speaker {i} reference text.",
            "audio_duration": 30.0,
            "sample_rate": 44100,
        }
    
    return features


def benchmark_engine(
    engine_class,
    engine_name: str,
    script: List[Dict[str, str]],
    speaker_features: Dict[str, Dict[str, any]],
    num_runs: int = 3,
) -> Dict[str, float]:
    """Benchmark a TTS engine."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking {engine_name}")
    logger.info(f"{'='*60}")
    
    # Initialize engine
    if engine_name == "Optimized":
        engine = engine_class(
            device=config.DEVICE,
            compile_models=True,
            use_half_precision=True,
            batch_size=None,  # Auto-detect
            max_workers=4,
        )
    else:
        engine = engine_class(device=config.DEVICE)
    
    # Warmup run
    logger.info("Performing warmup run...")
    if hasattr(engine, 'synthesize_speech_optimized'):
        _, _ = engine.synthesize_speech_optimized(
            script[:2],  # Just 2 segments for warmup
            speaker_features,
            use_parallel=True,
        )
    else:
        _, _ = engine.synthesize_speech(
            script[:2],
            speaker_features,
        )
    
    # Benchmark runs
    results = []
    for run in range(num_runs):
        logger.info(f"\nRun {run + 1}/{num_runs}")
        
        start_time = time.time()
        
        if hasattr(engine, 'synthesize_speech_optimized'):
            audio_data, caption_units = engine.synthesize_speech_optimized(
                script,
                speaker_features,
                use_parallel=True,
            )
        else:
            audio_data, caption_units = engine.synthesize_speech(
                script,
                speaker_features,
            )
        
        synthesis_time = time.time() - start_time
        
        # Calculate metrics
        audio_duration = len(audio_data) / 44100  # Assuming 44.1kHz
        rtf = synthesis_time / audio_duration if audio_duration > 0 else float('inf')
        
        results.append({
            "synthesis_time": synthesis_time,
            "audio_duration": audio_duration,
            "rtf": rtf,
            "segments": len(script),
        })
        
        logger.info(f"  Synthesis time: {synthesis_time:.2f}s")
        logger.info(f"  Audio duration: {audio_duration:.2f}s")
        logger.info(f"  Real-time factor: {rtf:.2f}x")
    
    # Calculate averages
    avg_synthesis_time = np.mean([r["synthesis_time"] for r in results])
    avg_audio_duration = np.mean([r["audio_duration"] for r in results])
    avg_rtf = np.mean([r["rtf"] for r in results])
    
    summary = {
        "engine": engine_name,
        "avg_synthesis_time": avg_synthesis_time,
        "avg_audio_duration": avg_audio_duration,
        "avg_rtf": avg_rtf,
        "meets_target": avg_audio_duration >= 30 and avg_synthesis_time <= 8,
        "runs": results,
    }
    
    return summary


def main():
    parser = argparse.ArgumentParser(description="Benchmark VoiceReel performance")
    parser.add_argument("--segments", type=int, default=15, help="Number of segments to synthesize")
    parser.add_argument("--runs", type=int, default=3, help="Number of benchmark runs")
    parser.add_argument("--output", type=str, help="Output JSON file for results")
    parser.add_argument("--engine", choices=["both", "regular", "optimized"], default="both",
                       help="Which engine to benchmark")
    args = parser.parse_args()
    
    # Generate test data
    logger.info("Generating test scripts...")
    script = generate_test_scripts(args.segments)
    speaker_features = create_dummy_speaker_features()
    
    # Calculate expected audio duration
    total_chars = sum(len(seg["text"]) for seg in script)
    estimated_duration = total_chars * 0.06  # Rough estimate: 0.06s per character
    logger.info(f"Script has {args.segments} segments, {total_chars} characters")
    logger.info(f"Estimated audio duration: {estimated_duration:.1f}s")
    
    results = {}
    
    # Benchmark regular engine
    if args.engine in ["both", "regular"]:
        try:
            regular_results = benchmark_engine(
                FishSpeechEngine,
                "Regular Fish-Speech",
                script,
                speaker_features,
                args.runs,
            )
            results["regular"] = regular_results
        except Exception as e:
            logger.error(f"Regular engine benchmark failed: {e}")
    
    # Benchmark optimized engine
    if args.engine in ["both", "optimized"]:
        try:
            optimized_results = benchmark_engine(
                OptimizedFishSpeechEngine,
                "Optimized Fish-Speech",
                script,
                speaker_features,
                args.runs,
            )
            results["optimized"] = optimized_results
        except Exception as e:
            logger.error(f"Optimized engine benchmark failed: {e}")
    
    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("BENCHMARK SUMMARY")
    logger.info(f"{'='*60}")
    
    for engine_name, result in results.items():
        logger.info(f"\n{engine_name.upper()} ENGINE:")
        logger.info(f"  Average synthesis time: {result['avg_synthesis_time']:.2f}s")
        logger.info(f"  Average audio duration: {result['avg_audio_duration']:.2f}s")
        logger.info(f"  Average RTF: {result['avg_rtf']:.2f}x")
        logger.info(f"  Meets 30s→8s target: {'✅ YES' if result['meets_target'] else '❌ NO'}")
    
    # Compare results
    if len(results) == 2:
        regular = results.get("regular", {})
        optimized = results.get("optimized", {})
        
        if regular and optimized:
            speedup = regular["avg_synthesis_time"] / optimized["avg_synthesis_time"]
            logger.info(f"\n{'='*60}")
            logger.info(f"OPTIMIZATION SPEEDUP: {speedup:.2f}x faster")
            logger.info(f"{'='*60}")
    
    # Save results
    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"\nResults saved to: {args.output}")
    
    # Check if we meet the PRD target
    logger.info(f"\n{'='*60}")
    logger.info("PRD PERFORMANCE TARGET CHECK:")
    logger.info("Goal: Generate 30 seconds of audio in ≤8 seconds")
    
    for engine_name, result in results.items():
        if result["avg_audio_duration"] >= 30:
            if result["avg_synthesis_time"] <= 8:
                logger.success(f"{engine_name}: ✅ PASS ({result['avg_synthesis_time']:.2f}s for {result['avg_audio_duration']:.2f}s audio)")
            else:
                logger.error(f"{engine_name}: ❌ FAIL ({result['avg_synthesis_time']:.2f}s for {result['avg_audio_duration']:.2f}s audio)")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()