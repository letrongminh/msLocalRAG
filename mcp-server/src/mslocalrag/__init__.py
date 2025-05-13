import asyncio
from . import server # Đảm bảo server.py nằm trong cùng thư mục mslocalrag

def main():
    """Main entry point for the package."""
    asyncio.run(server.main())

# Optionally expose other important items at package level
__all__ = ['main', 'server']