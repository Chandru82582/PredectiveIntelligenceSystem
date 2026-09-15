"""
ml/leakage_test.py
==================
Direct link to DataAnalysis.leakage_test suite.
"""
from DataAnalysis.leakage_test import (
    test_future_lookahead_leakage,
    test_split_boundary_contamination,
    test_target_proxy_correlations,
    test_accuracy_illusion_and_baselines,
    test_spatial_memorization_and_generalization,
    test_target_permutation_sanity,
    run_full_leakage_suite,
)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Telecom ML Data Leakage Audit")
    parser.add_argument("--sample-grids", type=int, default=500, help="Number of grids to sample (default: 500)")
    parser.add_argument("--full", action="store_true", help="Run on all 10,000 grids")
    args = parser.parse_args()

    grids = 10000 if args.full else args.sample_grids
    run_full_leakage_suite(sample_grids_count=grids)
