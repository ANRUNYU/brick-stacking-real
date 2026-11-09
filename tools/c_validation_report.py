"""Read JSON trial evidence and write a new, descriptive C validation report."""
import argparse,json
from pathlib import Path
from brick_stacking.planning.validation_report import summarize_trials


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    result=summarize_trials(json.loads(a.input.read_text(encoding='utf-8-sig')))
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
