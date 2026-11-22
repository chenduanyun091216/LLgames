"""启动 TTgames PC 端。"""
from pc.main import main


if __name__ == '__main__':
    import sys
    if '--lan-host' in sys.argv:
        from online.server.serve import run_native_host
        run_native_host()
    else:
        main()


