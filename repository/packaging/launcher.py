from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    import sys

    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        import traceback
        from pathlib import Path

        from inter_rater_analyzer.release_smoke import run

        target = Path(sys.argv[2])
        try:
            raise SystemExit(run(target))
        except Exception:
            target.mkdir(parents=True, exist_ok=True)
            (target / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise SystemExit(1) from None
    from inter_rater_analyzer.app import main

    raise SystemExit(main())
