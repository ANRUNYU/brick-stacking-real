"""Read-only local URDF inspection; install project first."""
import argparse
import json
from brick_stacking.hardware.urdf_inspection import inspect_urdf


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("urdf")
    args = p.parse_args()
    print(json.dumps(inspect_urdf(args.urdf), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
