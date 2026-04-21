from typing import Callable

from rich.console import Console
from rich.table import Table

from pacs.manager.validation_manager import ValidationManager

console = Console()


class TaskManager:
    def __init__(self, vm: ValidationManager):
        self.vm = vm
        self.tasks: list[tuple[Callable, tuple, dict, str]] = []
        self.pre_tasks: list[tuple[Callable, tuple, dict, str]] = []
        self.post_tasks: list[tuple[Callable, tuple, dict, str]] = []

    def add_task(self, task: Callable, description: str = "", *args, **kwargs) -> None:
        """
        Adds a task to the task manager.

        Args:
        -----
            task (Callable): The function to execute.
            description (str, optional): A description for the task.
            *args: Positional arguments for the function task.
            **kwargs: Keyword arguments for the function task.
        """
        self.tasks.append((task, args, kwargs, description))

    def add_pre_task(
        self, task: Callable, description: str = "", *args, **kwargs
    ) -> None:
        """
        Adds a task to the task manager that is executed prior to any other tasks.

        Args:
        -----
            task (Callable): The function to execute.
            description (str, optional): A description for the task.
            *args: Positional arguments for the function task.
            **kwargs: Keyword arguments for the function task.
        """
        self.pre_tasks.append((task, args, kwargs, description))

    def add_post_task(
        self, task: Callable, description: str = "", *args, **kwargs
    ) -> None:
        """
        Adds a task to the task manager that is executed after all the other tasks.

        Args:
        -----
            task (Callable): The function to execute.
            description (str, optional): A description for the task.
            *args: Positional arguments for the function task.
            **kwargs: Keyword arguments for the function task.
        """
        self.post_tasks.append((task, args, kwargs, description))

    def execute_tasks(self) -> None:
        """
        Executes all registered tasks.

        Args:
        -----
            vm (ValidationManager): The validation manager object
        """
        # Executing Validation Manager here means if there are any validation fails,
        # the tasks are never executed
        self.vm.execute()

        merged_task = self.pre_tasks + self.tasks + self.post_tasks

        if not merged_task:
            console.print("No actionable tasks found!\nSync Complete.", style="green")
            return

        for task, args, kwargs, description in merged_task:
            console.log(description)
            task(*args, **kwargs)

    def dry_run(self) -> None:
        """
        Simulates task execution without actually running them.
        """
        self.vm.execute()

        merged_task = self.pre_tasks + self.tasks + self.post_tasks

        if not merged_task:
            console.print("No actionable tasks found!", style="green")
            return

        table = Table(title="Dry Run Tasks", show_lines=True)
        table.add_column("S.N.", justify="left", style="cyan")
        table.add_column("Description", justify="left", style="green")

        for i, (_, _, _, description) in enumerate(merged_task):
            # task_name = task.__name__ if hasattr(task, "__name__") else "Unnamed Task"
            table.add_row(
                str(i + 1),
                description or "",
                # f"{task_name} with args = {args} and kwargs = {kwargs}",
            )

        # with console.pager():
        #     console.print(table)
        console.print(table)
