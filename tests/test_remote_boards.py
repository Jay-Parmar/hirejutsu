import importlib
import re

import pytest
import yaml

from hirejutsu import sources
from hirejutsu.config import template
from hirejutsu.sources import Source

BOARDS = [
    "remoteok",
    "remotive",
    "weworkremotely",
    "himalayas",
    "jobicy",
    "arbeitnow",
    "workingnomads",
    "hackernews",
    "fourdayweek",
]


def source_class(module_name):
    module = importlib.import_module(f"hirejutsu.sources.{module_name}")
    found = [value for value in vars(module).values()
             if isinstance(value, type) and issubclass(value, Source) and value is not Source]
    assert len(found) == 1
    return found[0]


@pytest.mark.parametrize("module_name", BOARDS)
def test_board_registers_a_source_with_a_label(module_name):
    cls = source_class(module_name)
    assert sources.available()[cls.name] is cls
    assert cls.label


def test_board_names_are_unique():
    names = [source_class(module_name).name for module_name in BOARDS]
    assert len(set(names)) == len(BOARDS)


def test_starter_config_examples_use_real_settings():
    lines = template().splitlines()
    start = lines.index("sources:")
    block = ["sources:"]
    for line in lines[start + 1:]:
        if not line.startswith("  "):
            break
        example = line.replace("# ", "", 1)
        if re.match(r"\s*[a-z_]+:", example):
            block.append(example)
    examples = yaml.safe_load("\n".join(block))["sources"]
    classes = sources.available()
    assert set(examples) <= set(classes)
    for name, settings in examples.items():
        if isinstance(settings, dict):
            assert set(settings) <= {"enabled", *classes[name].defaults}
