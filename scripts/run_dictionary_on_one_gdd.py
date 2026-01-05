
# scripts/run_dictionary_on_one_gdd.py
import argparse
from gdd_dictionary.dictionary_builder import build_dictionary_for_doc

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc_id", required=True, help="Document ID to build dictionary for")
    args = parser.parse_args()
    result = build_dictionary_for_doc(args.doc_id)
    print(result)

if __name__ == "__main__":
    main()
