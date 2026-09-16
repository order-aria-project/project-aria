from pathlib import Path

from core.app_registry import AppRegistry


TEST_PATH = Path("A:/Core/Project/config/test_applications.json")


registry = AppRegistry(TEST_PATH)

registry.register(
    "test app",
    r"C:\Example\TestApp.exe"
)

print("Registered:", registry.get("test app"))
print("All apps:", registry.all_apps())

registry.remove("test app")

if TEST_PATH.exists():
    TEST_PATH.unlink()

print("Registry test complete.")