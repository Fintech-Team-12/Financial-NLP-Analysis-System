from pathlib import Path


def main() -> None:
    raw_dir = Path("/workspace/data/raw")
    processed_dir = Path("/workspace/data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)
    print(f"raw_dir={raw_dir}")
    print(f"processed_dir={processed_dir}")
    print("ingest pipeline placeholder")


if __name__ == "__main__":
    main()
