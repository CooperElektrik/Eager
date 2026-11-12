from pathlib import Path

import pytest

from eager_script import (
    IncludeError,
    ParsedDialogue,
    ParsedLabel,
    parse_file,
    to_graph,
    validate,
)


def test_resolve_includes_inlines_scenes(tmp_path: Path):
    sub_file = tmp_path / "sub.es"
    sub_file.write_text(
        """## Sub Scene --- sub_scene
hoshiko: "Hello from included scene!"
<<
""",
        encoding="utf-8",
    )

    main_file = tmp_path / "main.es"
    main_file.write_text(
        f"""@include "{sub_file.name}"
## Start --- start
> sub_scene
""",
        encoding="utf-8",
    )

    items = parse_file(main_file)
    assert any(isinstance(it, ParsedLabel) and it.name == "sub_scene" for it in items)
    assert any(isinstance(it, ParsedDialogue) and it.speaker == "hoshiko" for it in items)

    graph = to_graph(items)
    assert "start" in graph.nodes
    assert "sub_scene" in graph.nodes
    val = validate(items)
    assert val.is_valid


def test_resolve_includes_circular_error(tmp_path: Path):
    file_a = tmp_path / "a.es"
    file_b = tmp_path / "b.es"
    file_a.write_text(f'@include "{file_b.name}"\n## A --- a\n<<\n', encoding="utf-8")
    file_b.write_text(f'@include "{file_a.name}"\n## B --- b\n<<\n', encoding="utf-8")

    with pytest.raises(IncludeError, match="Circular include"):
        parse_file(file_a)


def test_resolve_includes_missing_file_error(tmp_path: Path):
    main_file = tmp_path / "main.es"
    main_file.write_text('@include "nonexistent.es"\n## Start --- start\n<<\n', encoding="utf-8")

    with pytest.raises(IncludeError, match="Included file not found"):
        parse_file(main_file)
