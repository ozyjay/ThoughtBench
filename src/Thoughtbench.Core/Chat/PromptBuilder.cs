using Thoughtbench.Core.Knowledge;
using Thoughtbench.Core.Modeling;

namespace Thoughtbench.Core.Chat;

public static class PromptBuilder
{
    public static IReadOnlyList<ChatMessage> BuildMessages(
        string systemPrompt,
        IReadOnlyList<ChatMessage> conversation,
        string? currentUserMessage = null,
        string? retrievedContext = null)
    {
        var prompt = systemPrompt.Trim();
        if (!string.IsNullOrWhiteSpace(retrievedContext))
        {
            prompt = $"{prompt}{Environment.NewLine}{Environment.NewLine}{retrievedContext.Trim()}";
        }

        var messages = new List<ChatMessage> { new("system", prompt) };
        messages.AddRange(conversation);
        if (!string.IsNullOrWhiteSpace(currentUserMessage))
        {
            messages.Add(new ChatMessage("user", currentUserMessage.Trim()));
        }

        return messages;
    }

    public static string? RetrieveContextForMessage(KnowledgeIndex index, KnowledgeSettings settings, string userMessage)
    {
        var results = index.Retrieve(
            userMessage,
            settings.TopK,
            settings.MinimumScore,
            settings.MinimumMatchedTerms);
        return results.Count == 0 ? null : KnowledgeIndex.FormatRetrievedContext(results, settings.ContextCharBudget);
    }
}
