namespace Thoughtbench.Core.Diagnostics;

public static class DiagnosticsFormatter
{
    public static string FormatException(Exception exception) =>
        $"{exception.GetType().Name}: {exception.Message}{Environment.NewLine}{exception.StackTrace}".Trim();

    public static string FormatModelLoad(string displayName, string modelPath, string backend, string detail) =>
        $"Model: {displayName}{Environment.NewLine}Path: {modelPath}{Environment.NewLine}Backend: {backend}{Environment.NewLine}{detail}".Trim();
}
