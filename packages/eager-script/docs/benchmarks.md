# Benchmarks

Measurements for parsing, static validation, and JSON serialization across script scales:

| Script Scale | Line Count | File Size | AST Nodes | Parse Latency | Throughput | Peak Memory | Validation Time | JSON Export | Graph Build | Graph JSON |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Scene | 94 lines | 2.4 KB | 60 nodes | 0.06 ms | 1,643,000 lines/s | 12 KB | 0.01 ms | 0.02 ms | 0.01 ms | 0.01 ms |
| Chapter | 1,054 lines | 27.5 KB | 668 nodes | 0.57 ms | 1,858,000 lines/s | 102 KB | 0.06 ms | 0.23 ms | 0.10 ms | 0.13 ms |
| Full Episode | 10,504 lines | 278 KB | 6,653 nodes | 5.72 ms | 1,836,000 lines/s | 1.0 MB | 0.58 ms | 2.34 ms | 1.13 ms | 1.31 ms |
| Novel-Length | 52,504 lines | 1.4 MB | 33,253 nodes | 29.46 ms | 1,782,000 lines/s | 5.2 MB | 3.36 ms | 14.38 ms | 6.40 ms | 7.35 ms |

Hardware/Environment: Linux 7.1.12+deb14-amd64, Intel Core Ultra 9 288V, Python 3.14.

## Streaming Parser (`parse_iter`)

For stream-processing, low-memory runtimes, or interactive applications, `parse_iter` yields AST nodes iteratively with near-instantaneous startup (time to first node in microseconds) and minimal retained memory:

| Script Scale | Line Count | Peak Memory | Min Latency | Throughput | Time to First Node |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Scene | 94 lines | 6.4 KB | 0.06 ms | 1,631,000 lines/s | 0.0016 ms |
| Chapter | 1,054 lines | 6.5 KB | 0.58 ms | 1,804,000 lines/s | 0.0016 ms |
| Full Episode | 10,504 lines | 6.5 KB | 5.85 ms | 1,796,000 lines/s | 0.0017 ms |
| Novel-Length | 52,504 lines | 412 KB | 28.83 ms | 1,821,000 lines/s | 0.0019 ms |

> **Note**: Active working memory for `parse_iter` remains $O(1)$ (~6.5 KB). The allocation at 52k lines reflects CPython's internal `sys.intern` string dictionary resizing to accommodate thousands of unique scene identifiers.

## Running Benchmarks

```bash
PYTHONPATH=src python3 benchmarks/benchmark.py
```
