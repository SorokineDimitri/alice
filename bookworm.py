import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="bookworm",
        description="Moteur NLP pour creer des book cards Project Gutenberg.",
    )

    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--lexdiv", type=int, metavar="ID",
                         help="Mesures de diversite lexicale du livre")
    options.add_argument("--topics", type=int, metavar="ID",
                         help="Principaux topics par section")
    options.add_argument("--entities", type=int, metavar="ID",
                         help="Personnages et lieux du livre")
    options.add_argument("--summarize", type=int, metavar="ID",
                         help="Resume du livre en quelques phrases")
    options.add_argument("--similar", type=int, metavar="ID",
                         help="5 livres similaires (ordre decroissant)")
    options.add_argument("--card", type=int, metavar="ID",
                         help="Book card complete agregant tout le reste")

    args = parser.parse_args()

    try:
        result = run_task(args)
    except RuntimeError as exc:
        print(f"Erreur: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_task(args):
    if args.lexdiv is not None:
        from modules import lexdiv
        return lexdiv.run(args.lexdiv)
    if args.topics is not None:
        from modules import topics
        return topics.run(args.topics)
    if args.entities is not None:
        from modules import entities
        return entities.run(args.entities)
    if args.summarize is not None:
        from modules import summary
        return summary.run(args.summarize)
    if args.similar is not None:
        from modules import similarity
        return similarity.run(args.similar)
    if args.card is not None:
        from modules import card
        return card.run(args.card)


