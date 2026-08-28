# Focal prompt artifacts

These files define the checked focal-model interface used by the camera-grounded agent
harness. They are source artifacts, not empirical outputs.

The context contract has five semantic fields: `transcript`, `speaker_dynamics`,
`visual_scene`, `visual_attention`, and `modality_coverage`. T and M share ordered
windows, prompt structure, focal runtime, and decoding; only validated visual delivery
differs. Coverage is rendered in both conditions so missingness is explicit.

`system_prompt.txt` contains the fixed instruction template.
`context_window_schema.json` defines delivered context.
`output_schema.json` defines focal moment output.

The runtime manifest, exact endpoint, model layer, requests, responses, and results are
run-owned records and are not embedded in these prompt files. The versioned JSON
Schemas in `../schemas/v1/` define the corresponding runtime artifacts.
