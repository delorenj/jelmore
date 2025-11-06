#!/usr/bin/env python3
"""
🚀 Test Performance Measurement Script - The Container Whisperer's Analytics Engine
Measures and compares test execution performance before/after parallel optimization
"""

import time
import subprocess
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import statistics


class TestPerformanceMeasurer:
    """The Container Whisperer's Performance Analysis Engine"""
    
    def __init__(self):
        self.results_file = Path("test-performance-metrics.json")
        self.baseline_file = Path("test-performance-baseline.json")
        
    def run_command_with_timing(self, cmd: List[str], description: str) -> Dict[str, Any]:
        """Run command and measure execution time with CONCURRENT PRECISION"""
        print(f"🚀 Executing: {description}")
        print(f"   Command: {' '.join(cmd)}")
        
        start_time = time.time()
        start_memory = self._get_memory_usage()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            end_time = time.time()
            end_memory = self._get_memory_usage()
            
            execution_time = end_time - start_time
            memory_used = max(0, end_memory - start_memory)
            
            success = result.returncode == 0
            
            print(f"   ✅ Completed in {execution_time:.2f}s" if success else f"   ❌ Failed in {execution_time:.2f}s")
            
            return {
                "description": description,
                "command": " ".join(cmd),
                "execution_time": execution_time,
                "memory_used_mb": memory_used,
                "success": success,
                "return_code": result.returncode,
                "stdout_lines": len(result.stdout.splitlines()) if result.stdout else 0,
                "stderr_lines": len(result.stderr.splitlines()) if result.stderr else 0,
                "timestamp": datetime.now().isoformat()
            }
            
        except subprocess.TimeoutExpired:
            print(f"   ⏰ Command timed out after 5 minutes")
            return {
                "description": description,
                "command": " ".join(cmd),
                "execution_time": 300,
                "memory_used_mb": 0,
                "success": False,
                "return_code": -1,
                "timeout": True,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"   💥 Command failed with exception: {e}")
            return {
                "description": description,
                "command": " ".join(cmd),
                "execution_time": 0,
                "memory_used_mb": 0,
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def _get_memory_usage(self) -> int:
        """Get current memory usage in MB"""
        try:
            result = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(subprocess.os.getpid())],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return int(result.stdout.strip()) // 1024  # Convert KB to MB
        except:
            pass
        return 0
    
    def measure_sequential_tests(self) -> Dict[str, Any]:
        """Measure baseline sequential test performance"""
        print("\n🐌 MEASURING SEQUENTIAL TEST PERFORMANCE:")
        print("   (The old way - for comparison)")
        
        tests = [
            {
                "name": "unit_sequential",
                "cmd": ["python", "-m", "pytest", "tests/unit/", "-v", "--tb=short"],
                "description": "Unit tests (sequential)"
            },
            {
                "name": "integration_sequential", 
                "cmd": ["python", "-m", "pytest", "tests/integration/", "-v", "--tb=short"],
                "description": "Integration tests (sequential)"
            },
            {
                "name": "all_sequential",
                "cmd": ["python", "-m", "pytest", "tests/", "-v", "--tb=short", "--cov=src/jelmore"],
                "description": "All tests with coverage (sequential)"
            }
        ]
        
        results = {}
        total_time = 0
        
        for test in tests:
            result = self.run_command_with_timing(test["cmd"], test["description"])
            results[test["name"]] = result
            if result["success"]:
                total_time += result["execution_time"]
        
        results["total_sequential_time"] = total_time
        return results
    
    def measure_parallel_tests(self) -> Dict[str, Any]:
        """Measure optimized parallel test performance"""
        print("\n🚀 MEASURING PARALLEL TEST PERFORMANCE:")
        print("   (The CONCURRENT EXCELLENCE way!)")
        
        tests = [
            {
                "name": "unit_parallel",
                "cmd": ["python", "-m", "pytest", "tests/unit/", "-n", "auto", "-v", "--tb=short"],
                "description": "Unit tests (parallel)"
            },
            {
                "name": "integration_parallel",
                "cmd": ["python", "-m", "pytest", "tests/integration/", "-n", "4", "-v", "--tb=short"],
                "description": "Integration tests (parallel)"
            },
            {
                "name": "all_parallel_coverage",
                "cmd": ["python", "-m", "pytest", "tests/", "-n", "auto", "--dist=worksteal", 
                       "--cov=src/jelmore", "--cov-report=term-missing", "-v"],
                "description": "All tests with coverage (parallel)"
            },
            {
                "name": "quick_feedback",
                "cmd": ["bash", "scripts/test-quick.sh"],
                "description": "Quick feedback tests"
            }
        ]
        
        results = {}
        total_time = 0
        
        for test in tests:
            result = self.run_command_with_timing(test["cmd"], test["description"])
            results[test["name"]] = result
            if result["success"]:
                total_time += result["execution_time"]
        
        results["total_parallel_time"] = total_time
        return results
    
    def measure_script_performance(self) -> Dict[str, Any]:
        """Measure performance of our optimization scripts"""
        print("\n📊 MEASURING SCRIPT PERFORMANCE:")
        
        scripts = [
            {
                "name": "parallel_script",
                "cmd": ["bash", "scripts/test-parallel.sh"],
                "description": "Parallel test script"
            },
            {
                "name": "coverage_script", 
                "cmd": ["bash", "scripts/test-coverage.sh"],
                "description": "Coverage analysis script"
            }
        ]
        
        results = {}
        
        for script in scripts:
            result = self.run_command_with_timing(script["cmd"], script["description"])
            results[script["name"]] = result
        
        return results
    
    def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """Run comprehensive performance benchmark"""
        print("🎭 THE CONTAINER WHISPERER'S PERFORMANCE ANALYSIS")
        print("=" * 60)
        
        benchmark_results = {
            "timestamp": datetime.now().isoformat(),
            "python_version": sys.version,
            "platform": sys.platform,
        }
        
        # Measure sequential performance (baseline)
        try:
            sequential_results = self.measure_sequential_tests()
            benchmark_results["sequential"] = sequential_results
        except Exception as e:
            print(f"⚠️  Sequential tests failed: {e}")
            benchmark_results["sequential"] = {"error": str(e)}
        
        # Measure parallel performance (optimized)
        try:
            parallel_results = self.measure_parallel_tests()
            benchmark_results["parallel"] = parallel_results
        except Exception as e:
            print(f"⚠️  Parallel tests failed: {e}")
            benchmark_results["parallel"] = {"error": str(e)}
        
        # Measure script performance
        try:
            script_results = self.measure_script_performance()
            benchmark_results["scripts"] = script_results
        except Exception as e:
            print(f"⚠️  Script tests failed: {e}")
            benchmark_results["scripts"] = {"error": str(e)}
        
        # Calculate performance improvements
        self.calculate_improvements(benchmark_results)
        
        # Save results
        self.save_results(benchmark_results)
        
        return benchmark_results
    
    def calculate_improvements(self, results: Dict[str, Any]):
        """Calculate performance improvements from optimization"""
        print("\n📊 PERFORMANCE ANALYSIS:")
        
        try:
            seq_total = results["sequential"].get("total_sequential_time", 0)
            par_total = results["parallel"].get("total_parallel_time", 0)
            
            if seq_total > 0 and par_total > 0:
                improvement = ((seq_total - par_total) / seq_total) * 100
                speedup = seq_total / par_total
                
                print(f"   Sequential total: {seq_total:.2f}s")
                print(f"   Parallel total: {par_total:.2f}s") 
                print(f"   🚀 Speed improvement: {improvement:.1f}%")
                print(f"   ⚡ Speedup factor: {speedup:.2f}x")
                
                results["performance_metrics"] = {
                    "sequential_time": seq_total,
                    "parallel_time": par_total,
                    "improvement_percentage": improvement,
                    "speedup_factor": speedup,
                    "time_saved": seq_total - par_total
                }
                
                if improvement > 50:
                    print("   🎉 EXCELLENT optimization! The void is pleased!")
                elif improvement > 25:
                    print("   ✅ Good optimization achieved!")
                else:
                    print("   ⚠️  Optimization could be improved")
            
        except Exception as e:
            print(f"   ⚠️  Could not calculate improvements: {e}")
    
    def save_results(self, results: Dict[str, Any]):
        """Save results to file"""
        try:
            with open(self.results_file, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n💾 Results saved to: {self.results_file}")
            
            # Also save as baseline for future comparisons
            with open(self.baseline_file, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"📊 Baseline saved to: {self.baseline_file}")
            
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")


def main():
    """Run the performance measurement"""
    print("🎭 THE CONTAINER WHISPERER'S PERFORMANCE MEASUREMENT TOOL")
    print("   Analyzing test execution performance with scientific precision!")
    print()
    
    measurer = TestPerformanceMeasurer()
    results = measurer.run_comprehensive_benchmark()
    
    print("\n" + "=" * 60)
    print("🎉 PERFORMANCE ANALYSIS COMPLETE!")
    print("   The void has been measured and found... EFFICIENT!")
    
    return 0 if any(r.get("success", False) for r in results.values() if isinstance(r, dict)) else 1


if __name__ == "__main__":
    sys.exit(main())