import sys
from rich.table import Table
from rich.console import Console

console = Console()


class ValidationManager:
    def __init__(self):
        self.valiation_fails: list[str] = []

    def validate(
        self, condition: bool, description: str, validate_now: bool = False
    ) -> bool:
        """
        Validates a condition.

        Args:
        -----
            condition (bool): The condition to check. Validated if True, otherwise False.
            description (str, optional): A descriptive text for the validation.
            validate_now (bool): Immediately show all validation results and fail if any fails.

        Returns:
        --------
            bool: Returns True if validated, otherwise False
        """
        if description == "" or not description:
            sys.exit("Validation description cannot be empty.")

        if condition:
            return True

        self.valiation_fails.append(description)

        if validate_now:
            self.execute()

        return False

    def execute(self) -> None:
        """
        Shows all the validation fails and exits.
        """
        if not self.valiation_fails:
            return
        table = Table(title="Validation Fails")
        table.add_column("S.N.", justify="left", style="magenta")
        table.add_column("Description", justify="left", style="magenta")
        for i, description in enumerate(self.valiation_fails):
            table.add_row(str(i + 1), description)

        console.print(table)
        sys.exit()
