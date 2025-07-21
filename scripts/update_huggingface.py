import argparse
import os

from dotenv import load_dotenv
from huggingface_hub import upload_folder


def main():
    # Load environment variables from .env file
    load_dotenv()

    parser = argparse.ArgumentParser(description="Upload a folder to the Hugging Face Hub.")
    parser.add_argument(
        "--repo-id",
        required=True,
        help="Hugging Face dataset repo ID (e.g. stepmanai/ffr_charts)",
    )
    parser.add_argument("--folder", required=True, help="Local folder path to upload")
    parser.add_argument(
        "--repo-type",
        default="dataset",
        choices=["dataset", "model", "space"],
        help="Type of Hugging Face repo (default: dataset)",
    )
    parser.add_argument("--token", default=os.getenv("HF_TOKEN"), help="Hugging Face access token")

    args = parser.parse_args()

    if not args.token:
        raise ValueError()

    upload_folder(
        folder_path=args.folder,
        repo_id=args.repo_id,
        repo_type=args.repo_type,
        token=args.token,
    )

    print(f"✅ Successfully uploaded to: https://huggingface.co/{args.repo_type}s/{args.repo_id}")


if __name__ == "__main__":
    main()
