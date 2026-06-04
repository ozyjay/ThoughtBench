using System.Text;

namespace Thoughtbench.Core.Modeling;

public sealed record ParsedModelResponse(string? Thinking, string Content);

public static class ModelResponseParser
{
    private static readonly string[] ThoughtMarkers =
    [
        "<think>",
        "<|channel>thought",
        "<|channel> thought",
        "<|channel|>thought",
        "<|channel|> thought",
        "<thought|>",
        "<|channel>thinking",
        "<|channel> thinking",
        "<|channel|>thinking",
        "<|channel|> thinking",
        "<thinking|>",
        "<|channel>analysis",
        "<|channel> analysis",
        "<|channel|>analysis",
        "<|channel|> analysis",
        "<analysis|>"
    ];

    private static readonly string[] ResponseMarkers =
    [
        "</think>",
        "<channel|>",
        "<|channel>response",
        "<|channel> response",
        "<|channel|>response",
        "<|channel|> response",
        "<response|>",
        "<|channel>final",
        "<|channel> final",
        "<|channel|>final",
        "<|channel|> final",
        "<final|>",
        "<|channel>answer",
        "<|channel> answer",
        "<|channel|>answer",
        "<|channel|> answer",
        "<answer|>"
    ];

    private static readonly string[] TurnMarkers = ["<turn|>", "<|turn>", "<|im_end|>", "<|endoftext|>"];

    public static ParsedModelResponse Split(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
        {
            return new ParsedModelResponse(null, string.Empty);
        }

        var thinking = new StringBuilder();
        var response = new StringBuilder();
        var buffer = raw.Replace("\\n", "\n");
        var inThinking = false;

        for (var index = 0; index < buffer.Length;)
        {
            if (TryConsume(buffer, index, ThoughtMarkers, out var thoughtLength))
            {
                inThinking = true;
                index += thoughtLength;
                continue;
            }

            if (TryConsume(buffer, index, ResponseMarkers, out var responseLength))
            {
                inThinking = false;
                index += responseLength;
                continue;
            }

            if (TryConsume(buffer, index, TurnMarkers, out var turnLength))
            {
                inThinking = false;
                index += turnLength;
                continue;
            }

            if (inThinking)
            {
                thinking.Append(buffer[index]);
            }
            else
            {
                response.Append(buffer[index]);
            }

            index++;
        }

        var thinkingText = StripSpecialTokens(thinking.ToString()).Trim();
        var responseText = StripSpecialTokens(response.ToString()).Trim();
        if (string.IsNullOrEmpty(responseText) && !string.IsNullOrEmpty(thinkingText))
        {
            responseText = StripSpecialTokens(raw).Trim();
            thinkingText = string.Empty;
        }

        return new ParsedModelResponse(
            string.IsNullOrWhiteSpace(thinkingText) ? null : thinkingText,
            responseText);
    }

    public static string StripSpecialTokens(string text)
    {
        var cleaned = text;
        foreach (var marker in ThoughtMarkers.Concat(ResponseMarkers).Concat(TurnMarkers))
        {
            cleaned = cleaned.Replace(marker, string.Empty, StringComparison.Ordinal);
        }

        return cleaned.Trim();
    }

    private static bool TryConsume(string text, int index, IReadOnlyList<string> markers, out int length)
    {
        foreach (var marker in markers.OrderByDescending(static marker => marker.Length))
        {
            if (text.AsSpan(index).StartsWith(marker, StringComparison.Ordinal))
            {
                length = marker.Length;
                return true;
            }
        }

        length = 0;
        return false;
    }
}
