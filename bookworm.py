import argparse
import json
import sys


TASK_MODULES = {
    "lexdiv": "lexdiv",
    "topics": "topics",
    "entities": "entities",
    "summarize": "summary",
    "similar": "similarity",
    "card": "card",
}


def main():
    parser = argparse.ArgumentParser(
        prog="bookworm",
        description="Moteur NLP pour creer des book cards Project Gutenberg.",
    )

    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--lexdiv", type=int, metavar="ID",
                         help="Mesures de diversite lexicale du livre")
    options.add_argument("--topics", type=int, metavar="ID",
                         help="Principaux topics du livre")
    options.add_argument("--entities", type=int, metavar="ID",
                         help="Personnages et lieux du livre")
    options.add_argument("--summarize", type=int, metavar="ID",
                         help="Resume du livre en quelques phrases")
    options.add_argument("--similar", type=int, metavar="ID",
                         help="5 livres similaires (ordre decroissant)")
    options.add_argument("--card", type=int, metavar="ID",
                         help="Book card complete agregant tout le reste")
    parser.add_argument("--force", action="store_true",
                        help="Regenerer le cache JSON au lieu de le reutiliser")

    args = parser.parse_args()

    try:
        result = run_task(args)
    except RuntimeError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1

    # Une chaine (ex. --summarize) est affichee brute pour rendre les sauts
    # de ligne ; les dict/list gardent le format JSON.
    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_task(args):
    for task, module_name in TASK_MODULES.items():
        book_id = getattr(args, task)
        if book_id is not None:
            module = __import__(f"modules.{module_name}", fromlist=["run"])
            try:
                if task == "similar" and hasattr(module, "prepare"):
                    module.prepare(book_id)
                return module.run(book_id, force=args.force)
            except AttributeError:
                raise RuntimeError(f"--{task} is not implemented yet.")
    raise RuntimeError("No task selected.")


if __name__ == "__main__":
    raise SystemExit(main())
