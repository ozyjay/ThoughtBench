using System.Text.Json;
using Thoughtbench.Core.Modeling;

namespace Thoughtbench.Core.Profiles;

public sealed class ProfileStore
{
    public const int SystemPromptHistoryLimit = 50;

    public string ProfileDirectory { get; }

    public ProfileStore(string profileDirectory)
    {
        ProfileDirectory = Path.GetFullPath(profileDirectory);
        ProfilePaths.EnsureProfile(ProfileDirectory);
    }

    public async Task<string> LoadSystemPromptAsync(CancellationToken cancellationToken = default)
    {
        var path = ProfilePaths.SystemPromptPath(ProfileDirectory);
        return File.Exists(path)
            ? (await File.ReadAllTextAsync(path, cancellationToken)).Trim()
            : "You are a helpful assistant.";
    }

    public async Task SaveSystemPromptAsync(string prompt, string source = "edited", CancellationToken cancellationToken = default)
    {
        var path = ProfilePaths.SystemPromptPath(ProfileDirectory);
        var previous = File.Exists(path) ? await File.ReadAllTextAsync(path, cancellationToken) : string.Empty;
        if (!string.IsNullOrWhiteSpace(previous) && !string.Equals(previous.Trim(), prompt.Trim(), StringComparison.Ordinal))
        {
            await RememberPromptVersionAsync(previous.Trim(), source, cancellationToken);
        }

        await File.WriteAllTextAsync(path, prompt.Trim(), cancellationToken);
    }

    public async Task<IReadOnlyList<SystemPromptHistoryEntry>> LoadSystemPromptHistoryAsync(CancellationToken cancellationToken = default)
    {
        var path = ProfilePaths.SystemPromptHistoryPath(ProfileDirectory);
        if (!File.Exists(path))
        {
            return [];
        }

        try
        {
            return JsonSerializer.Deserialize<List<SystemPromptHistoryEntry>>(
                await File.ReadAllTextAsync(path, cancellationToken),
                JsonDefaults.Options) ?? [];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    public async Task RememberPromptVersionAsync(string content, string source, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(content))
        {
            return;
        }

        var history = (await LoadSystemPromptHistoryAsync(cancellationToken)).ToList();
        if (history.Any(entry => string.Equals(entry.Content, content, StringComparison.Ordinal)))
        {
            return;
        }

        history.Insert(0, new SystemPromptHistoryEntry(DateTimeOffset.Now, source, content));
        history = history.Take(SystemPromptHistoryLimit).ToList();
        await File.WriteAllTextAsync(
            ProfilePaths.SystemPromptHistoryPath(ProfileDirectory),
            JsonSerializer.Serialize(history, JsonDefaults.Options),
            cancellationToken);
    }

    public async Task<IReadOnlyList<ChatMessage>> LoadConversationAsync(CancellationToken cancellationToken = default)
    {
        var path = ProfilePaths.ConversationPath(ProfileDirectory);
        if (!File.Exists(path))
        {
            return [];
        }

        try
        {
            return JsonSerializer.Deserialize<List<ChatMessage>>(
                await File.ReadAllTextAsync(path, cancellationToken),
                JsonDefaults.Options) ?? [];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    public Task SaveConversationAsync(IReadOnlyList<ChatMessage> messages, CancellationToken cancellationToken = default) =>
        File.WriteAllTextAsync(
            ProfilePaths.ConversationPath(ProfileDirectory),
            JsonSerializer.Serialize(messages, JsonDefaults.Options),
            cancellationToken);

    public Task ClearConversationAsync(CancellationToken cancellationToken = default) =>
        SaveConversationAsync([], cancellationToken);

    public Task AppendLogEntryAsync(string kind, string content, CancellationToken cancellationToken = default)
    {
        var text = $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss}] {kind}{Environment.NewLine}{content.Trim()}{Environment.NewLine}{Environment.NewLine}";
        return File.AppendAllTextAsync(ProfilePaths.TranscriptPath(ProfileDirectory), text, cancellationToken);
    }

    public Task AppendDiagnosticsAsync(string content, CancellationToken cancellationToken = default)
    {
        var text = $"[{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss}] {content.Trim()}{Environment.NewLine}";
        return File.AppendAllTextAsync(ProfilePaths.DiagnosticsLogPath(ProfileDirectory), text, cancellationToken);
    }
}

public sealed record SystemPromptHistoryEntry(DateTimeOffset CreatedAt, string Source, string Content);
