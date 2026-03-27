"""Unit tests for services/workflow.py — no external dependencies."""
import pytest

from app.services.workflow import (
    list_workflows,
    load_template,
    merge_params,
    validate_params,
)


def test_list_workflows_returns_txt2img():
    workflows = list_workflows()
    assert "txt2img-sdxl" in workflows


def test_load_template_returns_graph_and_schema():
    graph, schema = load_template("txt2img-sdxl")
    assert isinstance(graph, dict)
    assert len(graph) > 0
    assert schema.id == "txt2img-sdxl"
    assert "positive_prompt" in schema.params
    assert "checkpoint" in schema.params


def test_load_template_unknown_raises():
    with pytest.raises(FileNotFoundError):
        load_template("does-not-exist")


def test_validate_params_passes_with_required():
    _, schema = load_template("txt2img-sdxl")
    # Should not raise — required params provided
    validate_params(schema, {"positive_prompt": "a cat", "checkpoint": "model.safetensors"})


def test_validate_params_raises_on_missing_required():
    _, schema = load_template("txt2img-sdxl")
    with pytest.raises(ValueError, match="checkpoint"):
        validate_params(schema, {"positive_prompt": "a cat"})


def test_validate_params_raises_on_missing_positive_prompt():
    _, schema = load_template("txt2img-sdxl")
    with pytest.raises(ValueError, match="positive_prompt"):
        validate_params(schema, {"checkpoint": "model.safetensors"})


def test_merge_params_injects_positive_prompt():
    graph, schema = load_template("txt2img-sdxl")
    merged = merge_params(graph, schema, {"positive_prompt": "a cat", "checkpoint": "model.safetensors"})
    # node "6" is CLIPTextEncode for positive prompt
    assert merged["6"]["inputs"]["text"] == "a cat"


def test_merge_params_injects_checkpoint():
    graph, schema = load_template("txt2img-sdxl")
    merged = merge_params(graph, schema, {"positive_prompt": "test", "checkpoint": "mymodel.safetensors"})
    assert merged["4"]["inputs"]["ckpt_name"] == "mymodel.safetensors"


def test_merge_params_injects_steps_and_cfg():
    graph, schema = load_template("txt2img-sdxl")
    merged = merge_params(
        graph, schema,
        {"positive_prompt": "test", "checkpoint": "m.safetensors", "steps": 30, "cfg": 9.0}
    )
    assert merged["10"]["inputs"]["steps"] == 30
    assert merged["10"]["inputs"]["cfg"] == 9.0


def test_merge_params_uses_defaults_for_optional():
    graph, schema = load_template("txt2img-sdxl")
    merged = merge_params(graph, schema, {"positive_prompt": "test", "checkpoint": "m.safetensors"})
    # steps default is 20
    assert merged["10"]["inputs"]["steps"] == 20


def test_merge_params_does_not_mutate_original():
    graph, schema = load_template("txt2img-sdxl")
    original_text = graph["6"]["inputs"]["text"]
    merge_params(graph, schema, {"positive_prompt": "mutate test", "checkpoint": "m.safetensors"})
    assert graph["6"]["inputs"]["text"] == original_text


def test_merge_params_injects_dimensions():
    graph, schema = load_template("txt2img-sdxl")
    merged = merge_params(
        graph, schema,
        {"positive_prompt": "test", "checkpoint": "m.safetensors", "width": 512, "height": 768}
    )
    assert merged["11"]["inputs"]["width"] == 512
    assert merged["11"]["inputs"]["height"] == 768
