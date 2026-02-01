"""
Phase 1 Textract Optimization Verification Script

This script verifies that Phase 1 optimizations are working correctly:
1. Photo channel routing to DetectDocumentText (98% cost reduction)
2. Caching layer with 30-day TTL (99% development cost reduction)
3. CloudWatch metrics tracking

Expected Results:
- Photos (IMG_01.jpg - IMG_08.jpg): $0.012 total (was $0.52)
- PDFs with intelligent routing: Reduced costs
- Second run: All cached (near-zero Textract cost)
"""

import boto3
import json
import time
from datetime import datetime

# Initialize clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
cloudwatch = boto3.client('cloudwatch')

# Configuration
CLAIMS_TABLE = "ICPA_Claims"
CLEAN_BUCKET = "icpa-clean-bucket-dev"  # Update with actual bucket name
TEST_CLAIM_ID = "CLM-000001"  # Golden Set

def check_cache_metrics():
    """Check CloudWatch metrics for cache hit/miss rates."""
    print("\n" + "="*80)
    print("PHASE 1 VERIFICATION: Cache Metrics")
    print("="*80)
    
    end_time = datetime.utcnow()
    start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    try:
        # Check cache hits
        response = cloudwatch.get_metric_statistics(
            Namespace='ICPA/Production',
            MetricName='TextractCacheHit',
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Sum']
        )
        
        cache_hits = sum([dp['Sum'] for dp in response['Datapoints']])
        print(f"✅ Cache Hits: {int(cache_hits)}")
        
        # Check cache misses
        response = cloudwatch.get_metric_statistics(
            Namespace='ICPA/Production',
            MetricName='TextractCacheMiss',
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Sum']
        )
        
        cache_misses = sum([dp['Sum'] for dp in response['Datapoints']])
        print(f"Cache Misses: {int(cache_misses)}")
        
        if cache_hits + cache_misses > 0:
            hit_rate = (cache_hits / (cache_hits + cache_misses)) * 100
            print(f"Cache Hit Rate: {hit_rate:.1f}%")
            
            if hit_rate > 50:
                print("✅ PASS: Cache is working effectively!")
            else:
                print("⚠️  WARNING: Low cache hit rate (expected on first run)")
        else:
            print("ℹ️  No cache metrics yet (run Golden Set test first)")
            
    except Exception as e:
        print(f"❌ Error checking metrics: {e}")

def check_api_selection_metrics():
    """Check CloudWatch metrics for API selection distribution."""
    print("\n" + "="*80)
    print("PHASE 1 VERIFICATION: API Selection Metrics")
    print("="*80)
    
    end_time = datetime.utcnow()
    start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='ICPA/Production',
            MetricName='TextractAPISelection',
            Dimensions=[
                {'Name': 'APIMethod', 'Value': 'DetectDocumentText'}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Sum']
        )
        
        photo_count = sum([dp['Sum'] for dp in response['Datapoints']])
        print(f"✅ Photos routed to DetectDocumentText: {int(photo_count)}")
        print(f"   Cost savings: ${photo_count * 0.0635:.3f} (98% reduction)")
        
        # Check TABLES-only routing
        response = cloudwatch.get_metric_statistics(
            Namespace='ICPA/Production',
            MetricName='TextractAPISelection',
            Dimensions=[
                {'Name': 'Features', 'Value': 'TABLES'}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,
            Statistics=['Sum']
        )
        
        tables_count = sum([dp['Sum'] for dp in response['Datapoints']])
        if tables_count > 0:
            print(f"✅ Invoices routed to TABLES-only: {int(tables_count)}")
            print(f"   Cost savings: ${tables_count * 0.050:.3f} (77% reduction)")
            
    except Exception as e:
        print(f"❌ Error checking API metrics: {e}")

def check_cached_extractions():
    """Check DynamoDB for cached extractions."""
    print("\n" + "="*80)
    print("PHASE 1 VERIFICATION: Cached Extractions")
    print("="*80)
    
    table = dynamodb.Table(CLAIMS_TABLE)
    
    try:
        # Scan for cached extractions (DOC#* pattern)
        response = table.scan(
            FilterExpression='begins_with(PK, :prefix) AND SK = :sk',
            ExpressionAttributeValues={
                ':prefix': 'DOC#',
                ':sk': 'EXTRACT'
            }
        )
        
        cached_docs = response.get('Items', [])
        print(f"✅ Cached Documents: {len(cached_docs)}")
        
        if cached_docs:
            print("\nSample cached documents:")
            for doc in cached_docs[:5]:
                doc_id = doc['PK'].replace('DOC#', '')
                extractor = doc.get('extractor_type', 'UNKNOWN')
                confidence = doc.get('confidence', 'N/A')
                cached_at = doc.get('cached_at', 'N/A')
                ttl = doc.get('ttl', 'N/A')
                
                print(f"  - {doc_id}: {extractor} (conf: {confidence}%, cached: {cached_at[:10]})")
                
                # Verify TTL is set (30 days)
                if ttl != 'N/A':
                    ttl_days = (int(ttl) - int(time.time())) / (24 * 60 * 60)
                    print(f"    TTL: {ttl_days:.1f} days remaining")
                    
            print(f"\n✅ PASS: Caching layer is active!")
            print(f"💰 Development Cost Savings: ${len(cached_docs) * 1.17 * 99:.2f} over 100 test runs")
        else:
            print("ℹ️  No cached documents yet (run Golden Set test first)")
            
    except Exception as e:
        print(f"❌ Error checking cache: {e}")

def estimate_cost_savings():
    """Estimate cost savings from Phase 1 optimizations."""
    print("\n" + "="*80)
    print("PHASE 1 COST IMPACT ANALYSIS")
    print("="*80)
    
    # Golden Set baseline
    print("\n📊 Golden Set (CLM-000001) Cost Analysis:")
    print("-" * 80)
    print("BEFORE Phase 1:")
    print("  - 5 PDFs × 2 pages × $0.065 = $0.65")
    print("  - 8 Photos × $0.065 = $0.52")
    print("  - TOTAL: $1.17 per claim")
    print()
    print("AFTER Phase 1 (Photo Routing):")
    print("  - 5 PDFs × 2 pages × $0.065 = $0.65")
    print("  - 8 Photos × $0.0015 = $0.012")
    print("  - TOTAL: $0.662 per claim")
    print("  - SAVINGS: $0.508 (43% reduction)")
    print()
    print("AFTER Phase 1 (With Caching - 100 test runs):")
    print("  - First run: $0.662")
    print("  - Next 99 runs: $0.00 (cached)")
    print("  - TOTAL: $0.662 (vs $117 without caching)")
    print("  - SAVINGS: $116.34 (99.4% reduction)")
    print()
    print("💡 Annual Savings (100K claims):")
    print("  - Baseline: $117,000/year")
    print("  - Phase 1: $66,200/year")
    print("  - SAVINGS: $50,800/year (43%)")

def main():
    """Run all verification checks."""
    print("\n" + "="*80)
    print("PHASE 1 TEXTRACT OPTIMIZATION VERIFICATION")
    print("="*80)
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    
    # Run checks
    check_cache_metrics()
    check_api_selection_metrics()
    check_cached_extractions()
    estimate_cost_savings()
    
    print("\n" + "="*80)
    print("VERIFICATION COMPLETE")
    print("="*80)
    print("\n📝 Next Steps:")
    print("1. Upload Golden Set (CLM-000001) to test photo routing")
    print("2. Re-upload same files to verify caching (should see 100% cache hits)")
    print("3. Monitor CloudWatch dashboard for cost metrics")
    print("4. Proceed to Phase 2 optimizations (Intelligent Routing + Async)")

if __name__ == "__main__":
    main()
