"""Benchmarking suite for eager-script parser, validator, and serializer."""

import gc
import statistics
import time
import tracemalloc
from collections.abc import Callable
from typing import Any

import eager_script

BASE_SCENE = """
## Scene {idx} --- scene_{idx}

# Ambient background comment
Narrator: The morning light filters through the ancient stained glass.
- Dust motes drift lazily through the silent air.
/ A distant bell chimes three times.

Alice (thoughtful): {{voice:alice_wake.ogg}} Is anyone awake yet?
Bob (smiling): I have been awake for hours, Alice.

~ trigger_morning_lighting
~ play_sfx church_bell.ogg

? Head downstairs to the tavern (tavern_{idx})
? Inspect the glowing bookshelf (library_{idx})

## Tavern {idx} --- tavern_{idx}
The tavern is lively with adventurers drinking ale.
>> greet_bartender
> finish_{idx}

## Library {idx} --- library_{idx}
Ancient tomes line the towering mahogany shelves.
Alice: Look at tome #1 on row #4! It is glowing.
> finish_{idx}

## Finished {idx} --- finish_{idx}
Narrator: The journey continues into the realm.
"""


def generate_screenplay(num_scenes: int) -> str:
    """Generate a realistic screenplay script with N scenes."""
    blocks = [BASE_SCENE.format(idx=i) for i in range(num_scenes)]
    # Add common subroutine at the end so >> greet_bartender and << are valid
    blocks.append("""
## Greet Bartender --- greet_bartender
Bartender: What can I get for you travelers?
<<
""")
    return "\n".join(blocks)


def benchmark_op(
    _name: str,
    func: Callable[[], Any],
    iterations: int = 20,
    warmup: int = 5,
) -> dict[str, float]:
    """Measure latency and memory allocation of an operation."""
    gc.collect()

    # Warmup
    for _ in range(warmup):
        func()

    # Memory measurement
    tracemalloc.start()
    tracemalloc.reset_peak()
    func()
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Timing measurement
    times: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        func()
        t1 = time.perf_counter()
        times.append(t1 - t0)

    mean_time = statistics.mean(times)
    median_time = statistics.median(times)
    min_time = min(times)

    return {
        "mean_ms": mean_time * 1000.0,
        "median_ms": median_time * 1000.0,
        "min_ms": min_time * 1000.0,
        "peak_kb": peak_bytes / 1024.0,
    }


def run_benchmarks() -> None:
    test_scales = [
        ("Small Scene (~100 lines)", 3),
        ("Short Story / Chapter (~1,000 lines)", 35),
        ("Full VN Episode (~10,000 lines)", 350),
        ("Novel-Length Script (~50,000 lines)", 1750),
    ]

    print("=" * 80)
    print("EAGER-S PARSER & RUNTIME BENCHMARK")
    print("=" * 80)

    for label, num_scenes in test_scales:
        script = generate_screenplay(num_scenes)
        line_count = len(script.splitlines())
        size_kb = len(script.encode("utf-8")) / 1024.0

        # Pre-parse for secondary benchmarks
        parsed_items = eager_script.parse(script)
        ast_count = len(parsed_items)

        # 1. Parse Benchmark
        parse_stats = benchmark_op(
            "Parse",
            lambda s=script: eager_script.parse(s),
            iterations=15 if line_count < 20000 else 5,
        )
        lines_per_sec = line_count / (parse_stats["min_ms"] / 1000.0)

        # 2. Validation Benchmark
        val_stats = benchmark_op(
            "Validate",
            lambda p=parsed_items: eager_script.validate(p),
            iterations=15 if line_count < 20000 else 5,
        )

        # 3. JSON Serialization Benchmark
        json_stats = benchmark_op(
            "To JSON",
            lambda p=parsed_items: eager_script.to_json(p, indent=None),
            iterations=15 if line_count < 20000 else 5,
        )

        # 4. Graph Construction Benchmark
        graph_stats = benchmark_op(
            "To Graph",
            lambda p=parsed_items: eager_script.to_graph(p),
            iterations=15 if line_count < 20000 else 5,
        )

        # Pre-build graph for export benchmarks
        graph = eager_script.to_graph(parsed_items)

        # 5. Graph JSON Export Benchmark
        graph_json_stats = benchmark_op(
            "Graph JSON",
            lambda g=graph: g.to_json(include_body=False, indent=None),
            iterations=15 if line_count < 20000 else 5,
        )

        print(f"\n--- {label} ---")
        print(f"  Script Size: {line_count:,} lines | {size_kb:.1f} KB | {ast_count:,} AST nodes")
        print(
            f"  [Parse]        Min: {parse_stats['min_ms']:6.2f} ms | "
            f"Avg: {parse_stats['mean_ms']:6.2f} ms | "
            f"Throughput: {lines_per_sec:,.0f} lines/sec | "
            f"Peak Mem: {parse_stats['peak_kb']:6.1f} KB"
        )
        print(
            f"  [Validate]     Min: {val_stats['min_ms']:6.2f} ms | "
            f"Avg: {val_stats['mean_ms']:6.2f} ms"
        )
        print(
            f"  [JSON Export]  Min: {json_stats['min_ms']:6.2f} ms | "
            f"Avg: {json_stats['mean_ms']:6.2f} ms"
        )
        print(
            f"  [To Graph]     Min: {graph_stats['min_ms']:6.2f} ms | "
            f"Avg: {graph_stats['mean_ms']:6.2f} ms"
        )
        print(
            f"  [Graph JSON]   Min: {graph_json_stats['min_ms']:6.2f} ms | "
            f"Avg: {graph_json_stats['mean_ms']:6.2f} ms"
        )

    print("\n" + "=" * 80)


if __name__ == "__main__":
    run_benchmarks()
