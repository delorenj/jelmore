#!/usr/bin/env python3
"""
Security validation script for Jelmore

This script validates that:
1. No hardcoded secrets exist in the codebase
2. Environment configuration is properly set up
3. Security best practices are followed
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any


class SecurityValidator:
    """Validates security configuration and practices"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def validate_all(self) -> bool:
        """Run all security validations"""
        print("🔍 Running security validation...")
        
        self.check_environment_config()
        self.check_hardcoded_secrets()
        self.check_gitignore()
        self.check_docker_config()
        self.validate_config_py()
        self.check_pre_commit_setup()
        
        self.report_results()
        return len(self.errors) == 0
    
    def check_environment_config(self):
        """Check environment configuration files"""
        env_example = self.project_root / ".env.example"
        
        if not env_example.exists():
            self.errors.append("❌ .env.example file is missing")
            return
        
        # Check for required security variables
        required_vars = [
            "POSTGRES_PASSWORD",
            "API_KEY_ADMIN",
            "API_KEY_CLIENT", 
            "API_KEY_READONLY"
        ]
        
        content = env_example.read_text()
        for var in required_vars:
            if var not in content:
                self.errors.append(f"❌ Required variable {var} missing from .env.example")
        
        # Check for insecure placeholder values
        insecure_patterns = [
            r"password.*=.*dev",
            r"key.*=.*123",
            r"secret.*=.*test",
            r"token.*=.*dev"
        ]
        
        for pattern in insecure_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                self.warnings.append(f"⚠️  Potentially insecure placeholder in .env.example: {pattern}")
    
    def check_hardcoded_secrets(self):
        """Scan for hardcoded secrets in source code"""
        source_dirs = ["src/", "scripts/"]
        
        # Patterns that indicate hardcoded secrets
        secret_patterns = [
            (r'password\s*=\s*["\'][^"\']*["\']', "hardcoded password"),
            (r'secret\s*=\s*["\'][^"\']*["\']', "hardcoded secret"),
            (r'token\s*=\s*["\'][^"\']*["\']', "hardcoded token"),
            (r'key\s*=\s*["\'][^"\']*["\']', "hardcoded key"),
            (r'api_key\s*=\s*["\'][^"\']*["\']', "hardcoded API key"),
        ]
        
        for dir_name in source_dirs:
            source_dir = self.project_root / dir_name
            if not source_dir.exists():
                continue
                
            for py_file in source_dir.rglob("*.py"):
                content = py_file.read_text()
                
                for pattern, description in secret_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Skip if it's clearly a placeholder or configuration
                        if any(placeholder in match.group(0).lower() 
                               for placeholder in ["field(", "getenv", "environ", "your-", "change-me", "example"]):
                            continue
                        
                        line_num = content[:match.start()].count('\n') + 1
                        self.errors.append(
                            f"❌ {description} found in {py_file}:{line_num}"
                        )
    
    def check_gitignore(self):
        """Validate .gitignore includes security patterns"""
        gitignore_path = self.project_root / ".gitignore"
        
        if not gitignore_path.exists():
            self.errors.append("❌ .gitignore file is missing")
            return
        
        content = gitignore_path.read_text()
        
        # Required security patterns
        security_patterns = [
            ".env",
            "*.key",
            "secrets/",
            ".secrets.baseline"
        ]
        
        for pattern in security_patterns:
            if pattern not in content:
                self.warnings.append(f"⚠️  Security pattern '{pattern}' missing from .gitignore")
    
    def check_docker_config(self):
        """Check Docker configuration for security issues"""
        docker_compose_path = self.project_root / "docker-compose.yml"
        
        if not docker_compose_path.exists():
            self.warnings.append("⚠️  docker-compose.yml not found")
            return
        
        content = docker_compose_path.read_text()
        
        # Check for fallback credentials
        if ":-" in content and ("password" in content.lower() or "key" in content.lower()):
            fallback_matches = re.finditer(r'\$\{[^}]+:-[^}]+\}', content)
            for match in fallback_matches:
                if any(keyword in match.group(0).lower() 
                       for keyword in ["password", "key", "secret", "token"]):
                    self.errors.append(
                        f"❌ Insecure fallback credential found in docker-compose.yml: {match.group(0)}"
                    )
    
    def validate_config_py(self):
        """Validate configuration module security"""
        config_path = self.project_root / "src" / "jelmore" / "config.py"
        
        if not config_path.exists():
            self.warnings.append("⚠️  config.py not found")
            return
        
        content = config_path.read_text()
        
        # Check for hardcoded defaults in Field definitions
        field_patterns = re.finditer(r'Field\([^)]*default\s*=\s*["\'][^"\']+["\'][^)]*\)', content)
        for match in field_patterns:
            field_def = match.group(0)
            if any(keyword in field_def.lower() for keyword in ["password", "secret", "key"]):
                # Skip if it's clearly a safe default
                if not any(safe in field_def.lower() for safe in ['""', "''", "localhost", "header"]):
                    self.errors.append(f"❌ Potentially hardcoded secret in config.py: {field_def}")
        
        # Check for validation methods
        if "model_post_init" not in content:
            self.warnings.append("⚠️  No validation method found in config.py")
    
    def check_pre_commit_setup(self):
        """Check pre-commit configuration"""
        pre_commit_path = self.project_root / ".pre-commit-config.yaml"
        
        if not pre_commit_path.exists():
            self.warnings.append("⚠️  .pre-commit-config.yaml not found (recommended for security)")
            return
        
        content = pre_commit_path.read_text()
        
        # Check for security-related hooks
        security_hooks = ["detect-secrets", "bandit", "ggshield"]
        for hook in security_hooks:
            if hook not in content:
                self.warnings.append(f"⚠️  Security hook '{hook}' not found in pre-commit config")
    
    def report_results(self):
        """Report validation results"""
        print(f"\n📊 Security Validation Results:")
        print(f"   Errors: {len(self.errors)}")
        print(f"   Warnings: {len(self.warnings)}")
        
        if self.errors:
            print("\n🚨 CRITICAL SECURITY ISSUES:")
            for error in self.errors:
                print(f"   {error}")
        
        if self.warnings:
            print("\n⚠️  SECURITY RECOMMENDATIONS:")
            for warning in self.warnings:
                print(f"   {warning}")
        
        if not self.errors and not self.warnings:
            print("\n✅ All security validations passed!")
        elif not self.errors:
            print("\n✅ No critical security issues found")
            print("   Consider addressing the warnings above")
        else:
            print(f"\n❌ {len(self.errors)} critical security issues must be fixed!")
            return False
        
        return True


def main():
    """Main entry point"""
    project_root = Path(__file__).parent.parent
    validator = SecurityValidator(project_root)
    
    success = validator.validate_all()
    
    if not success:
        print("\n🔧 To fix security issues:")
        print("   1. Remove all hardcoded secrets")
        print("   2. Use environment variables only") 
        print("   3. Update .env.example with secure placeholders")
        print("   4. Run this script again to validate")
        sys.exit(1)
    
    print("\n🛡️  Security validation complete!")


if __name__ == "__main__":
    main()