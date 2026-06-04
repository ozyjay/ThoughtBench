using Thoughtbench.Core.Chat;
using Thoughtbench.Core.Knowledge;
using Thoughtbench.Core.Modeling;
using Thoughtbench.Core.Profiles;
using Thoughtbench.Core.Runtime;

namespace Thoughtbench.Tests;

public static class Program
{
    public static async Task<int> Main()
    {
        var tests = new List<(string Name, Func<Task> Test)>
        {
            ("chunk_text_ignores_empty_text_and_keeps_metadata", TestChunkText),
            ("retrieve_ranks_exact_project_terms_highly", TestRetrieveRanking),
            ("retrieve_filters_stop_word_only_overlap", TestStopWords),
            ("settings_round_trip", TestSettingsRoundTrip),
            ("index_persistence_and_stale_detection", TestIndexPersistence),
            ("format_retrieved_context_respects_budget_and_sources", TestContextFormatting),
            ("profile_prompt_and_conversation_round_trip", TestProfileStore),
            ("response_parser_splits_thinking_and_content", TestResponseParser),
            ("token_usage_thresholds", TestTokenUsage),
            ("prompt_builder_injects_knowledge", TestPromptBuilder)
        };

        var failures = 0;
        foreach (var (name, test) in tests)
        {
            try
            {
                await test();
                Console.WriteLine($"PASS {name}");
            }
            catch (Exception ex)
            {
                failures++;
                Console.WriteLine($"FAIL {name}: {ex.Message}");
            }
        }

        Console.WriteLine($"{tests.Count - failures}/{tests.Count} tests passed.");
        return failures == 0 ? 0 : 1;
    }

    private static Task TestChunkText()
    {
        Assert.Equal(0, KnowledgeIndex.ChunkText("   ", "empty.md").Count);
        var chunks = KnowledgeIndex.ChunkText("Alpha beta gamma.\n\nDelta epsilon.", "notes.md", 3, 0);
        Assert.Equal("notes.md", chunks[0].Source);
        Assert.Equal("notes.md#0001", chunks[0].ChunkId);
        Assert.Equal("Alpha beta gamma.", chunks[0].Text);
        Assert.Equal("Delta epsilon.", chunks[1].Text);
        return Task.CompletedTask;
    }

    private static Task TestRetrieveRanking()
    {
        var index = KnowledgeIndex.FromChunks(
            ("setup.md#0001", "setup.md", "Setup-Thoughtbench.ps1 downloads models and respects HF_HOME."),
            ("style.md#0001", "style.md", "Use concise markdown answers for general writing tasks."));
        var results = index.Retrieve("How do I set HF_HOME for Setup-Thoughtbench.ps1?", topK: 2);
        Assert.Equal("setup.md", results[0].Chunk.Source);
        Assert.True(results[0].Score > 0, "Expected a positive BM25 score.");
        return Task.CompletedTask;
    }

    private static Task TestStopWords()
    {
        var index = KnowledgeIndex.FromChunks(("notes.md#0001", "notes.md", "Use concise markdown answers for general writing tasks."));
        Assert.Equal(0, index.Retrieve("What is this for?", topK: 3).Count);
        return Task.CompletedTask;
    }

    private static async Task TestSettingsRoundTrip()
    {
        using var sandbox = new Sandbox();
        var settings = new KnowledgeSettings(3, 1200, 20, 5, 0.75, 2);
        await KnowledgeIndex.SaveSettingsAsync(sandbox.ProfileDirectory, settings);
        Assert.Equal(settings, await KnowledgeIndex.LoadSettingsAsync(sandbox.ProfileDirectory));
    }

    private static async Task TestIndexPersistence()
    {
        using var sandbox = new Sandbox();
        var knowledge = ProfilePaths.KnowledgeFolder(sandbox.ProfileDirectory);
        Directory.CreateDirectory(knowledge);
        var note = Path.Combine(knowledge, "notes.md");
        await File.WriteAllTextAsync(note, "first version");
        var built = await KnowledgeIndex.BuildAsync(sandbox.ProfileDirectory);
        var loaded = await KnowledgeIndex.LoadAsync(sandbox.ProfileDirectory);
        Assert.Equal(built.Chunks[0].Text, loaded.Chunks[0].Text);
        Assert.False(KnowledgeIndex.IsStale(sandbox.ProfileDirectory, loaded));
        await Task.Delay(20);
        await File.WriteAllTextAsync(note, "second version with extra text");
        Assert.True(KnowledgeIndex.IsStale(sandbox.ProfileDirectory, loaded), "Expected changed knowledge file to mark index stale.");
    }

    private static Task TestContextFormatting()
    {
        var index = KnowledgeIndex.FromChunks(
            ("a.md#0001", "a.md", string.Join(' ', Enumerable.Repeat("alpha", 100))),
            ("b.md#0001", "b.md", "beta policy"));
        var context = KnowledgeIndex.FormatRetrievedContext(index.Retrieve("alpha beta policy", topK: 2), 180);
        Assert.Contains("Retrieved knowledge files", context);
        Assert.Contains("[a.md#0001]", context);
        Assert.True(context.Length <= 220, "Context exceeded relaxed budget.");
        return Task.CompletedTask;
    }

    private static async Task TestProfileStore()
    {
        using var sandbox = new Sandbox();
        var store = new ProfileStore(sandbox.ProfileDirectory);
        await store.SaveSystemPromptAsync("Be concise.");
        Assert.Equal("Be concise.", await store.LoadSystemPromptAsync());
        await store.SaveConversationAsync([new ChatMessage("user", "hello")]);
        var messages = await store.LoadConversationAsync();
        Assert.Equal("hello", messages[0].Content);
    }

    private static Task TestResponseParser()
    {
        var parsed = ModelResponseParser.Split("<think>plan</think>final answer<|endoftext|>");
        Assert.Equal("plan", parsed.Thinking);
        Assert.Equal("final answer", parsed.Content);
        return Task.CompletedTask;
    }

    private static Task TestTokenUsage()
    {
        Assert.Equal(TokenUsageState.Normal, TokenUsage.Format(100, 100, 1000).State);
        Assert.Equal(TokenUsageState.Warning, TokenUsage.Format(760, 100, 1000).State);
        Assert.Equal(TokenUsageState.Critical, TokenUsage.Format(960, 10, 1000).State);
        Assert.True(TokenUsage.Format(1000, 1, 1000).PromptOverLimit, "Prompt over-limit flag should be true.");
        return Task.CompletedTask;
    }

    private static Task TestPromptBuilder()
    {
        var messages = PromptBuilder.BuildMessages(
            "Rules",
            [new ChatMessage("assistant", "old")],
            "new question",
            "Retrieved knowledge files:\n[a.md#0001] Alpha");
        Assert.Contains("Retrieved knowledge files", messages[0].Content);
        Assert.Equal("new question", messages[^1].Content);
        return Task.CompletedTask;
    }
}

internal sealed class Sandbox : IDisposable
{
    public string ProfileDirectory { get; } =
        Path.Combine("tests", "tmp_csharp", $"profile_{Guid.NewGuid():N}");

    public Sandbox()
    {
        Directory.CreateDirectory(ProfileDirectory);
    }

    public void Dispose()
    {
        if (Directory.Exists(ProfileDirectory))
        {
            Directory.Delete(ProfileDirectory, recursive: true);
        }
    }
}

internal static class Assert
{
    public static void Equal<T>(T expected, T actual)
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
        {
            throw new InvalidOperationException($"Expected {expected}, got {actual}.");
        }
    }

    public static void True(bool condition, string message)
    {
        if (!condition)
        {
            throw new InvalidOperationException(message);
        }
    }

    public static void False(bool condition)
    {
        if (condition)
        {
            throw new InvalidOperationException("Expected false.");
        }
    }

    public static void Contains(string expected, string actual)
    {
        if (!actual.Contains(expected, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"Expected text to contain {expected}.");
        }
    }
}
