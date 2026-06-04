namespace Thoughtbench.Core.Runtime;

public enum TokenUsageState
{
    Normal,
    Warning,
    Critical
}

public sealed record TokenUsageResult(string Text, TokenUsageState State, bool PromptOverLimit);

public static class TokenUsage
{
    public static TokenUsageResult Format(
        int promptTokens,
        int reservedTokens,
        int contextLimit,
        int liveReplyTokens = 0)
    {
        var replyWindowTokens = Math.Max(reservedTokens, liveReplyTokens);
        var usedTokens = promptTokens + replyWindowTokens;
        var pct = contextLimit > 0 ? usedTokens / (double)contextLimit * 100 : 0;
        var promptOverLimit = promptTokens >= contextLimit;
        var state = promptOverLimit || pct >= 95
            ? TokenUsageState.Critical
            : pct >= 80
                ? TokenUsageState.Warning
                : TokenUsageState.Normal;
        var replyText = liveReplyTokens > 0
            ? $"reply {liveReplyTokens:N0}/{reservedTokens:N0}"
            : $"reply budget {reservedTokens:N0}";

        return new TokenUsageResult(
            $"Tokens: {usedTokens:N0}/{contextLimit:N0} ({pct:0}%) - input {promptTokens:N0} + {replyText}",
            state,
            promptOverLimit);
    }
}
