import sys
from typing import List


class Program:
    @staticmethod
    def main(args: List[str]) -> None:
        print("Для отображения языка в репозитории")


if __name__ == "__main__":
    Program.main(sys.argv[1:])
