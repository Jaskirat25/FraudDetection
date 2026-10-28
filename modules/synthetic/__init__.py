"""
modules/synthetic - Synthetic Card Generation & Benchmark Evaluation Subsystem.
"""
from .card_renderer import render_synthetic_aadhaar_card, generate_demographic_identity
from .degradations import (
    apply_gaussian_blur,
    apply_motion_blur,
    apply_glare,
    apply_perspective_warp,
    apply_jpeg_compression,
    apply_screen_moire,
    apply_random_degradation
)
from .attack_generators import generate_attack_sample, ATTACK_VECTORS
from .benchmark_runner import BenchmarkRunner, BenchmarkReport
