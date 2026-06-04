using System.Text.Json;

namespace Thoughtbench.Core.Profiles;

public static class ProfilePaths
{
    public const string AppName = "Thoughtbench";
    public const string AppFolderName = ".thoughtbench";
    public const string SystemPromptFileName = "system_prompt.md";
    public const string SystemPromptHistoryFileName = "system_prompt_history.json";
    public const string ConversationFileName = "conversation.json";
    public const string KnowledgeFolderName = "knowledge";
    public const string KnowledgeIndexFolderName = "knowledge_index";
    public const string KnowledgeSettingsFileName = "knowledge_settings.json";

    public static string SettingsDirectory =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), AppName);

    public static string SettingsPath => Path.Combine(SettingsDirectory, "settings.json");

    public static string DefaultProfilesRoot =>
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), AppFolderName, "profiles");

    public static string ProfileLabel(string profileDirectory)
    {
        var label = Path.GetFileName(profileDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
        return string.IsNullOrWhiteSpace(label) ? profileDirectory : label;
    }

    public static string SystemPromptPath(string profileDirectory) =>
        Path.Combine(profileDirectory, SystemPromptFileName);

    public static string SystemPromptHistoryPath(string profileDirectory) =>
        Path.Combine(profileDirectory, SystemPromptHistoryFileName);

    public static string ConversationPath(string profileDirectory) =>
        Path.Combine(profileDirectory, ConversationFileName);

    public static string KnowledgeFolder(string profileDirectory) =>
        Path.Combine(profileDirectory, KnowledgeFolderName);

    public static string KnowledgeIndexFolder(string profileDirectory) =>
        Path.Combine(profileDirectory, KnowledgeIndexFolderName);

    public static string KnowledgeIndexPath(string profileDirectory) =>
        Path.Combine(KnowledgeIndexFolder(profileDirectory), "index.json");

    public static string KnowledgeSettingsPath(string profileDirectory) =>
        Path.Combine(profileDirectory, KnowledgeSettingsFileName);

    public static string DiagnosticsLogPath(string profileDirectory) =>
        Path.Combine(profileDirectory, "diagnostics.log");

    public static string TranscriptPath(string profileDirectory) =>
        Path.Combine(profileDirectory, $"chat-{DateTime.Now:yyyyMMdd}.log");

    public static void EnsureProfile(string profileDirectory)
    {
        Directory.CreateDirectory(profileDirectory);
        Directory.CreateDirectory(KnowledgeFolder(profileDirectory));
        Directory.CreateDirectory(KnowledgeIndexFolder(profileDirectory));

        var promptPath = SystemPromptPath(profileDirectory);
        if (!File.Exists(promptPath))
        {
            File.WriteAllText(promptPath, "You are a helpful assistant.");
        }
    }

    public static async Task<string> ResolveActiveProfileAsync(CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(SettingsDirectory);

        if (File.Exists(SettingsPath))
        {
            try
            {
                var settings = JsonSerializer.Deserialize<AppSettings>(
                    await File.ReadAllTextAsync(SettingsPath, cancellationToken),
                    JsonDefaults.Options);
                if (!string.IsNullOrWhiteSpace(settings?.ActiveProfileDirectory))
                {
                    EnsureProfile(settings.ActiveProfileDirectory);
                    return settings.ActiveProfileDirectory;
                }
            }
            catch (JsonException)
            {
                // Invalid settings are replaced with a default profile below.
            }
        }

        var profile = Path.Combine(DefaultProfilesRoot, "Default");
        EnsureProfile(profile);
        await SaveActiveProfileAsync(profile, cancellationToken);
        return profile;
    }

    public static async Task SaveActiveProfileAsync(string profileDirectory, CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(SettingsDirectory);
        var resolved = Path.GetFullPath(profileDirectory);
        var recent = new List<string> { resolved };
        if (File.Exists(SettingsPath))
        {
            try
            {
                var existing = JsonSerializer.Deserialize<AppSettings>(
                    await File.ReadAllTextAsync(SettingsPath, cancellationToken),
                    JsonDefaults.Options);
                if (existing?.RecentProfileDirectories is not null)
                {
                    recent.AddRange(existing.RecentProfileDirectories);
                }
            }
            catch (JsonException)
            {
                // Replace invalid settings.
            }
        }

        var settings = new AppSettings(
            resolved,
            recent.Distinct(StringComparer.OrdinalIgnoreCase).Take(12).ToArray());
        await File.WriteAllTextAsync(
            SettingsPath,
            JsonSerializer.Serialize(settings, JsonDefaults.Options),
            cancellationToken);
    }
}

public sealed record AppSettings(string ActiveProfileDirectory, string[] RecentProfileDirectories);

public static class JsonDefaults
{
    public static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };
}
