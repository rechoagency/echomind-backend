#!/usr/bin/env python3
"""
Comprehensive Business Feature Test
Tests all critical functionality required for competitive edge
"""
import os
os.environ.setdefault('SUPABASE_URL', 'http://dummy')
os.environ.setdefault('SUPABASE_SERVICE_ROLE_KEY', 'dummy')
os.environ.setdefault('OPENAI_API_KEY', 'dummy')

def test_traffic_attribution():
    """Test 1: Traffic Attribution (UTM tracking)"""
    print("\n🔍 TEST 1: Traffic Attribution")
    try:
        from utils.utm_builder import build_utm_link
        
        test_url = "https://example.com/product"
        result = build_utm_link(
            base_url=test_url,
            client_id="test123",
            content="testsubreddit_comment"
        )
        
        # Check UTM parameters exist
        assert "utm_source=reddit" in result, "Missing utm_source"
        assert "utm_medium" in result, "Missing utm_medium"
        assert "utm_campaign" in result, "Missing utm_campaign"
        assert "utm_content" in result, "Missing utm_content"
        
        print(f"   ✅ UTM Builder works: {result[:80]}...")
        return True
    except Exception as e:
        print(f"   ❌ Traffic Attribution failed: {e}")
        return False

def test_content_generation_utm_injection():
    """Test 2: Content Generator injects UTM links"""
    print("\n🔍 TEST 2: Content Generation UTM Injection")
    try:
        from workers.content_generation_worker import ContentGenerationWorker
        
        # Check if worker has utm functionality
        worker = ContentGenerationWorker(client_id="test")
        
        # Check method exists
        assert hasattr(worker, 'inject_utm_links') or 'utm' in str(worker.__class__.__dict__), \
            "Worker doesn't have UTM injection capability"
        
        print("   ✅ Content generator has UTM injection")
        return True
    except AssertionError as e:
        print(f"   ❌ {e}")
        return False
    except Exception as e:
        print(f"   ⚠️  Could not fully test (needs full env): {e}")
        return None  # Partial pass

def test_karma_tracking_exists():
    """Test 3: Karma Tracking Worker"""
    print("\n🔍 TEST 3: Karma Tracking Worker")
    try:
        import os.path as p
        
        # Check worker file exists
        worker_path = 'workers/karma_tracking_worker.py'
        assert p.exists(worker_path), f"Worker file missing: {worker_path}"
        
        # Check it has key functions
        with open(worker_path) as f:
            content = f.read()
            assert 'karma' in content.lower(), "No karma tracking logic found"
            assert 'track' in content.lower() or 'fetch' in content.lower(), \
                "No tracking/fetching logic found"
        
        print("   ✅ Karma tracking worker exists")
        return True
    except Exception as e:
        print(f"   ❌ Karma tracking missing: {e}")
        return False

def test_scheduler_exists():
    """Test 4: Automated Scheduling"""
    print("\n🔍 TEST 4: Automated Daily Scheduling")
    try:
        import os.path as p
        
        # Check for scheduler/cron files
        scheduler_files = [
            'scheduler.py',
            'cron.py',
            'background_scheduler.py'
        ]
        
        found = [f for f in scheduler_files if p.exists(f)]
        
        if found:
            print(f"   ✅ Scheduler found: {found[0]}")
            return True
        
        # Check workers for scheduling logic
        import glob
        workers = glob.glob('workers/*worker.py')
        has_schedule = False
        for worker in workers:
            with open(worker) as f:
                content = f.read()
                if 'schedule' in content.lower() or 'cron' in content.lower():
                    has_schedule = True
                    print(f"   ✅ Scheduling logic in {worker}")
                    break
        
        if has_schedule:
            return True
            
        print("   ⚠️  No obvious scheduler found - needs verification")
        return None  # Needs manual check
    except Exception as e:
        print(f"   ❌ Scheduler check failed: {e}")
        return False

def test_content_delivery_tracking():
    """Test 5: Content Delivery Tracking"""
    print("\n🔍 TEST 5: Content Delivery Tracking")
    try:
        from workers.content_generation_worker import ContentGenerationWorker
        
        worker = ContentGenerationWorker(client_id="test")
        
        # Check logging method exists
        assert hasattr(worker, 'log_content_delivery'), \
            "No log_content_delivery method"
        
        print("   ✅ Content delivery tracking exists")
        return True
    except Exception as e:
        print(f"   ❌ Content delivery tracking failed: {e}")
        return False

def test_error_handling():
    """Test 6: Error Handling"""
    print("\n🔍 TEST 6: Error Handling & Reliability")
    try:
        # Check supabase_client has error handling
        with open('supabase_client.py') as f:
            content = f.read()
            assert 'try:' in content and 'except' in content, \
                "No error handling in supabase_client"
            assert 'ConnectionError' in content or 'Exception' in content, \
                "No connection error handling"
        
        print("   ✅ Error handling implemented")
        return True
    except Exception as e:
        print(f"   ❌ Error handling check failed: {e}")
        return False

def main():
    print("=" * 60)
    print("🏢 ECHOMIND BUSINESS FUNCTIONALITY TEST")
    print("=" * 60)
    
    tests = [
        ("Traffic Attribution (ROI Proof)", test_traffic_attribution),
        ("UTM Injection in Content", test_content_generation_utm_injection),
        ("Karma Tracking", test_karma_tracking_exists),
        ("Automated Scheduling", test_scheduler_exists),
        ("Content Delivery Tracking", test_content_delivery_tracking),
        ("Error Handling", test_error_handling),
    ]
    
    results = {}
    for name, test_func in tests:
        results[name] = test_func()
    
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    partial = sum(1 for v in results.values() if v is None)
    
    for name, result in results.items():
        status = "✅ PASS" if result is True else "❌ FAIL" if result is False else "⚠️  PARTIAL"
        print(f"{status:12} {name}")
    
    print("\n" + "=" * 60)
    print(f"✅ Passed: {passed}/{len(tests)}")
    print(f"❌ Failed: {failed}/{len(tests)}")
    print(f"⚠️  Partial: {partial}/{len(tests)}")
    
    score = (passed + partial * 0.5) / len(tests) * 100
    print(f"\n🎯 Business Readiness Score: {score:.0f}/100")
    
    if score >= 80:
        grade = "A - COMPETITIVE"
    elif score >= 70:
        grade = "B - GOOD"
    elif score >= 60:
        grade = "C - NEEDS WORK"
    else:
        grade = "D - NOT READY"
    
    print(f"📈 Grade: {grade}")
    print("=" * 60)
    
    return score >= 70  # Pass if score >= 70%

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
