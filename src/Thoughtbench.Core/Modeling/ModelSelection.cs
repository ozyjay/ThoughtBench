namespace Thoughtbench.Core.Modeling;

public sealed record ModelSelection(string DisplayName, string ModelPath, string Backend = "onnx-cuda");
