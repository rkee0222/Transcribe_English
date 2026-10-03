"""Windows entry point; no server or development tool required."""
if __name__ == "__main__":
    import os
    import sys
    # Console-less Windows builds have no standard streams; media libraries
    # may still write diagnostic messages. User-facing errors use GUI dialogs.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    from transcriber.gui import main
    main()
