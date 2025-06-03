#!/usr/bin/env python3
"""Benchmark tool for VoiceReel performance optimization."""

import argparse
import json
import os
import sys
import time
from typing import Dict, List

import numpy as np
from loguru import logger

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voicereel.fish_speech_integration import get_fish_speech_engine, get_speaker_manager
from voicereel.fish_speech_optimized import get_optimized_engine
from voicereel.performance_optimizer import get_performance_monitor, setup_optimizations


def create_test_script(num_segments: int = 15, avg_words_per_segment: int = 20) -> List[Dict[str, str]]:
    """Create a test script for benchmarking.
    
    Args:
        num_segments: Number of segments in the script
        avg_words_per_segment: Average words per segment
        
    Returns:
        Test script with speaker assignments
    """
    # Sample text variations
    sample_texts = [
        "The quick brown fox jumps over the lazy dog in the sunny afternoon.",
        "Machine learning models have revolutionized natural language processing tasks.",
        "VoiceReel provides high-quality multi-speaker text-to-speech synthesis.",
        "Performance optimization is crucial for real-time audio generation systems.",
        "Advanced neural networks enable realistic voice cloning capabilities.",
    ]
    
    script = []
    speakers = ["spk_1", "spk_2", "spk_3"]  # Simulate 3 speakers
    
    for i in range(num_segments):
        # Rotate through sample texts and speakers
        text = sample_texts[i % len(sample_texts)]
        
        # Adjust text length to match target word count
        words = text.split()
        if len(words) < avg_words_per_segment:
            # Repeat to reach target length
            multiplier = avg_words_per_segment // len(words) + 1
            words = (words * multiplier)[:avg_words_per_segment]
        else:
            words = words[:avg_words_per_segment]
        
        script.append({
            "speaker_id": speakers[i % len(speakers)],
            "text": " ".join(words)
        })
    
    return script


def create_dummy_speaker_features(speaker_ids: List[str]) -> Dict[str, Dict[str, any]]:
    """Create dummy speaker features for testing."""
    features = {}
    for speaker_id in speaker_ids:
        features[speaker_id] = {
            "embeddings": np.random.randn(256).tolist(),  # Dummy embeddings
            "sample_rate": 48000,
            "voice_characteristics": {
                "pitch": np.random.uniform(0.8, 1.2),
                "speed": np.random.uniform(0.9, 1.1),
            }
        }
    return features


def benchmark_synthesis(engine, script: List[Dict[str, str]], 
                       speaker_features: Dict[str, Dict[str, any]],
                       name: str = "Engine") -> Dict[str, float]:
    """Benchmark synthesis performance.
    
    Args:
        engine: Speech synthesis engine
        script: Test script
        speaker_features: Speaker feature dictionary
        name: Engine name for logging
        
    Returns:
        Performance metrics
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Benchmarking {name}")
    logger.info(f"{'='*60}")
    
    # Warmup run
    logger.info("Performing warmup run...")
    if hasattr(engine, 'synthesize_speech_optimized'):
        _, _ = engine.synthesize_speech_optimized(
            script[:2], speaker_features, use_parallel=True
        )
    else:
        _, _ = engine.synthesize_speech(script[:2], speaker_features)
    
    # Actual benchmark
    logger.info(f"Running benchmark with {len(script)} segments...")
    start_time = time.time()
    
    if hasattr(engine, 'synthesize_speech_optimized'):
        audio_data, caption_units = engine.synthesize_speech_optimized(
            script, speaker_features, use_parallel=True
        )
    else:
        audio_data, caption_units = engine.synthesize_speech(script, speaker_features)
    
    synthesis_time = time.time() - start_time
    
    # Calculate metrics
    total_duration = caption_units[-1]["end"] if caption_units else 0.0
    rtf = synthesis_time / total_duration if total_duration > 0 else float('inf')
    
    # Log results
    logger.info(f"\nResults for {name}:")
    logger.info(f"  Total segments: {len(script)}")
    logger.info(f"  Audio duration: {total_duration:.2f}s")
    logger.info(f"  Synthesis time: {synthesis_time:.2f}s")
    logger.info(f"  Real-time factor: {rtf:.2f}x")
    logger.info(f"  Throughput: {total_duration/synthesis_time:.2f}x realtime")
    
    # Check performance target
    if total_duration >= 30:
        if synthesis_time <= 8:
            logger.success(f"✅ PASS: 30s audio synthesized in {synthesis_time:.2f}s (target: ≤8s)")
        else:
            logger.error(f"❌ FAIL: 30s audio took {synthesis_time:.2f}s (target: ≤8s)")
    
    return {
        "name": name,
        "segments": len(script),
        "audio_duration": total_duration,
        "synthesis_time": synthesis_time,
        "rtf": rtf,
        "throughput": total_duration / synthesis_time if synthesis_time > 0 else 0,
        "meets_target": total_duration >= 30 and synthesis_time <= 8
    }


def main():
    """Run VoiceReel performance benchmark."""
    parser = argparse.ArgumentParser(description="Benchmark VoiceReel performance")
    parser.add_argument("--segments", type=int, default=15, 
                       help="Number of segments to synthesize")
    parser.add_argument("--words-per-segment", type=int, default=20,
                       help="Average words per segment")
    parser.add_argument("--compare", action="store_true",
                       help="Compare standard vs optimized engine")
    parser.add_argument("--output", type=str,
                       help="Save results to JSON file")
    parser.add_argument("--device", type=str, default="cuda",
                       help="Device to use (cuda/cpu)")
    args = parser.parse_args()
    
    # Setup
    logger.info("VoiceReel Performance Benchmark")
    logger.info(f"Device: {args.device}")
    
    # Create test data
    script = create_test_script(args.segments, args.words_per_segment)
    total_words = sum(len(seg["text"].split()) for seg in script)
    estimated_duration = total_words * 0.15  # Rough estimate: 0.15s per word
    
    logger.info(f"Test script: {len(script)} segments, ~{total_words} words")
    logger.info(f"Estimated audio duration: ~{estimated_duration:.1f}s")
    
    # Get unique speakers and create features
    unique_speakers = list(set(seg["speaker_id"] for seg in script))
    speaker_features = create_dummy_speaker_features(unique_speakers)
    
    results = []
    
    if args.compare:
        # Benchmark standard engine
        logger.info("\nLoading standard Fish-Speech engine...")
        standard_engine = get_fish_speech_engine()
        standard_results = benchmark_synthesis(
            standard_engine, script, speaker_features, "Standard Engine"
        )
        results.append(standard_results)
        
        # Benchmark optimized engine
        logger.info("\nLoading optimized Fish-Speech engine...")
        optimized_engine = get_optimized_engine()
        optimized_results = benchmark_synthesis(
            optimized_engine, script, speaker_features, "Optimized Engine"
        )
        results.append(optimized_results)
        
        # Compare results
        logger.info(f"\n{'='*60}")
        logger.info("COMPARISON SUMMARY")
        logger.info(f"{'='*60}")
        
        speedup = standard_results["synthesis_time"] / optimized_results["synthesis_time"]
        logger.info(f"Speedup: {speedup:.2f}x")
        logger.info(f"Standard: {standard_results['synthesis_time']:.2f}s")
        logger.info(f"Optimized: {optimized_results['synthesis_time']:.2f}s")
        
    else:
        # Only benchmark optimized engine
        logger.info("\nLoading optimized Fish-Speech engine...")
        optimized_engine = get_optimized_engine()
        optimized_results = benchmark_synthesis(
            optimized_engine, script, speaker_features, "Optimized Engine"
        )
        results.append(optimized_results)
    
    # Get performance monitor stats if available
    monitor = get_performance_monitor()
    if monitor.metrics:
        logger.info(f"\n{'='*60}")
        logger.info("PERFORMANCE METRICS")
        logger.info(f"{'='*60}")
        monitor.log_summary()
    
    # Save results if requested
    if args.output:
        with open(args.output, "w") as f:
            json.dump({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "config": {
                    "segments": args.segments,
                    "words_per_segment": args.words_per_segment,
                    "device": args.device
                },
                "results": results
            }, f, indent=2)
        logger.info(f"\nResults saved to {args.output}")
    
    # Final verdict
    logger.info(f"\n{'='*60}")
    if any(r["meets_target"] for r in results):
        logger.success("🎉 Performance target achieved!")
    else:
        logger.warning("⚠️  Performance target not met. Further optimization needed.")


if __name__ == "__main__":
    main()