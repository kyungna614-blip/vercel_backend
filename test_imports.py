"""Quick import check."""
import sys
sys.path.insert(0, ".")

try:
    from app.main import app
    print("All imports OK")
    print("Total routes:", len(app.routes))
    api_routes = [r for r in app.routes if hasattr(r, "path") and "/api/" in getattr(r, "path", "")]
    for r in api_routes:
        methods = getattr(r, "methods", set())
        print("  %s %s" % (",".join(methods), r.path))
    print("\nServer ready to start.")
except Exception as e:
    print("IMPORT ERROR: %s" % e)
    import traceback
    traceback.print_exc()
