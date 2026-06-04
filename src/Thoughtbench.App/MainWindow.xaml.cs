using System.Text;
using System.Windows;
using Microsoft.Win32;
using System.IO;
using Thoughtbench.Core.Chat;
using Thoughtbench.Core.Diagnostics;
using Thoughtbench.Core.Knowledge;
using Thoughtbench.Core.Modeling;
using Thoughtbench.Core.Profiles;
using Thoughtbench.Core.Runtime;
using Thoughtbench.Onnx;

namespace Thoughtbench.App;

public partial class MainWindow : Window
{
    private readonly OnnxModelRuntime _runtime = new();
    private ProfileStore? _profile;
    private KnowledgeIndex _knowledgeIndex = KnowledgeIndex.Empty();
    private KnowledgeSettings _knowledgeSettings = KnowledgeSettings.Default;
    private readonly List<ChatMessage> _conversation = [];
    private CancellationTokenSource? _generationCts;
    private string? _pendingSteer;
    private bool _modelLoaded;

    public MainWindow()
    {
        InitializeComponent();
        Loaded += async (_, _) => await InitializeAsync();
        Closed += (_, _) => _runtime.Dispose();
    }

    private async Task InitializeAsync()
    {
        try
        {
            var profileDirectory = await ProfilePaths.ResolveActiveProfileAsync();
            await LoadProfileAsync(profileDirectory);
            StatusText.Text = "Ready. Select an ONNX GenAI model folder and load it.";
        }
        catch (Exception ex)
        {
            ShowError(ex);
        }
    }

    private async Task LoadProfileAsync(string profileDirectory)
    {
        _profile = new ProfileStore(profileDirectory);
        ProfilePathBox.Text = _profile.ProfileDirectory;
        BehaviourBox.Text = await _profile.LoadSystemPromptAsync();
        _conversation.Clear();
        _conversation.AddRange(await _profile.LoadConversationAsync());
        _knowledgeSettings = await KnowledgeIndex.LoadSettingsAsync(_profile.ProfileDirectory);
        _knowledgeIndex = await KnowledgeIndex.LoadAsync(_profile.ProfileDirectory);
        if (KnowledgeIndex.IsStale(_profile.ProfileDirectory, _knowledgeIndex, _knowledgeSettings))
        {
            _knowledgeIndex = await KnowledgeIndex.BuildAsync(_profile.ProfileDirectory, _knowledgeSettings);
        }

        RenderConversation();
        KnowledgeStatusText.Text = $"Knowledge: {_knowledgeIndex.Chunks.Count} chunks";
        await ProfilePaths.SaveActiveProfileAsync(_profile.ProfileDirectory);
    }

    private void BrowseModel_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog
        {
            Title = "Choose ONNX GenAI model folder"
        };
        if (dialog.ShowDialog(this) == true)
        {
            ModelPathBox.Text = dialog.FolderName;
        }
    }

    private async void LoadModel_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            StatusText.Text = "Loading ONNX CUDA model...";
            var modelPath = OnnxModelRuntime.ResolveModelDirectory(ModelPathBox.Text.Trim());
            ModelPathBox.Text = modelPath;
            var selection = new ModelSelection("Selected ONNX model", modelPath);
            await _runtime.LoadAsync(selection, CancellationToken.None);
            _modelLoaded = true;
            StatusText.Text = $"Loaded {selection.DisplayName}";
            DiagnosticsBox.AppendText(DiagnosticsFormatter.FormatModelLoad(selection.DisplayName, selection.ModelPath, selection.Backend, "ONNX Runtime GenAI CUDA") + Environment.NewLine);
            await UpdateTokenStatsAsync();
        }
        catch (Exception ex)
        {
            ShowError(ex);
        }
    }

    private async void OpenProfile_Click(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog
        {
            Title = "Choose Thoughtbench profile folder"
        };
        if (dialog.ShowDialog(this) == true)
        {
            await LoadProfileAsync(dialog.FolderName);
            StatusText.Text = $"Profile: {ProfilePaths.ProfileLabel(dialog.FolderName)}";
        }
    }

    private async void NewProfile_Click(object sender, RoutedEventArgs e)
    {
        var root = ProfilePaths.DefaultProfilesRoot;
        Directory.CreateDirectory(root);
        var path = Path.Combine(root, $"Profile {DateTime.Now:yyyyMMdd HHmmss}");
        await LoadProfileAsync(path);
        StatusText.Text = $"Profile: {ProfilePaths.ProfileLabel(path)}";
    }

    private async void RebuildKnowledge_Click(object sender, RoutedEventArgs e)
    {
        if (_profile is null)
        {
            return;
        }

        try
        {
            StatusText.Text = "Rebuilding knowledge index...";
            _knowledgeIndex = await KnowledgeIndex.BuildAsync(_profile.ProfileDirectory, _knowledgeSettings);
            KnowledgeStatusText.Text = $"Knowledge: {_knowledgeIndex.Chunks.Count} chunks";
            StatusText.Text = "Knowledge index rebuilt.";
        }
        catch (Exception ex)
        {
            ShowError(ex);
        }
    }

    private async void Send_Click(object sender, RoutedEventArgs e)
    {
        var userText = InputBox.Text.Trim();
        if (_generationCts is not null)
        {
            if (!string.IsNullOrWhiteSpace(userText))
            {
                _pendingSteer = userText;
                InputBox.Clear();
            }

            _generationCts.Cancel();
            StatusText.Text = "Stopping current generation...";
            return;
        }

        if (string.IsNullOrWhiteSpace(userText))
        {
            return;
        }

        await SendUserMessageAsync(userText);
    }

    private void Stop_Click(object sender, RoutedEventArgs e)
    {
        _generationCts?.Cancel();
        StatusText.Text = "Stopping...";
    }

    private async void ClearConversation_Click(object sender, RoutedEventArgs e)
    {
        _conversation.Clear();
        RenderConversation();
        if (_profile is not null)
        {
            await _profile.ClearConversationAsync();
        }

        await UpdateTokenStatsAsync();
        StatusText.Text = "Conversation cleared.";
    }

    private async void RewriteBehaviour_Click(object sender, RoutedEventArgs e)
    {
        var advice = InputBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(advice))
        {
            StatusText.Text = "Type behaviour advice first.";
            return;
        }

        var current = BehaviourBox.Text.Trim();
        BehaviourBox.Text = $"{current}{Environment.NewLine}{Environment.NewLine}- {advice}".Trim();
        InputBox.Clear();
        if (_profile is not null)
        {
            await _profile.SaveSystemPromptAsync(BehaviourBox.Text, "rewrite");
            await _profile.AppendLogEntryAsync("Behaviour Rewrite", $"Advice:{Environment.NewLine}{advice}{Environment.NewLine}{Environment.NewLine}Updated behaviour:{Environment.NewLine}{BehaviourBox.Text}");
        }

        StatusText.Text = "Assistant behaviour updated.";
        await UpdateTokenStatsAsync();
    }

    private async Task SendUserMessageAsync(string userText)
    {
        if (!_modelLoaded)
        {
            StatusText.Text = "Load an ONNX model first.";
            return;
        }

        if (_profile is null)
        {
            return;
        }

        InputBox.Clear();
        await _profile.SaveSystemPromptAsync(BehaviourBox.Text);
        var retrievedContext = PromptBuilder.RetrieveContextForMessage(_knowledgeIndex, _knowledgeSettings, userText);
        var messagesForRuntime = PromptBuilder.BuildMessages(BehaviourBox.Text, _conversation, userText, retrievedContext);
        _conversation.Add(new ChatMessage("user", userText));
        await _profile.SaveConversationAsync(_conversation);
        await _profile.AppendLogEntryAsync("User", userText);
        RenderConversation();
        if (!string.IsNullOrWhiteSpace(retrievedContext))
        {
            AppendChat($"System: {retrievedContext}{Environment.NewLine}{Environment.NewLine}");
        }

        _generationCts = new CancellationTokenSource();
        SendButton.Content = "Steer";
        StatusText.Text = "Generating...";
        var responseBuilder = new StringBuilder();
        var progress = new Progress<GenerationChunk>(chunk =>
        {
            if (chunk.Channel == GenerationChannel.Thinking)
            {
                ThinkingOutputBox.AppendText(chunk.Text);
            }
            else
            {
                responseBuilder.Append(chunk.Text);
                ChatBox.AppendText(chunk.Text);
                ChatBox.ScrollToEnd();
            }
        });

        AppendChat("Assistant: ");
        try
        {
            var response = await _runtime.GenerateAsync(messagesForRuntime, ReadGenerationOptions(), progress, _generationCts.Token);
            var finalText = string.IsNullOrWhiteSpace(response) ? responseBuilder.ToString().Trim() : response.Trim();
            _conversation.Add(new ChatMessage("assistant", finalText));
            await _profile.SaveConversationAsync(_conversation);
            await _profile.AppendLogEntryAsync("Assistant", finalText);
            AppendChat(Environment.NewLine + Environment.NewLine);
            StatusText.Text = "Ready.";
        }
        catch (OperationCanceledException)
        {
            var partial = responseBuilder.ToString().Trim();
            if (!string.IsNullOrWhiteSpace(partial))
            {
                _conversation.Add(new ChatMessage("assistant", partial + " [interrupted]"));
                await _profile.SaveConversationAsync(_conversation);
            }

            AppendChat(Environment.NewLine + "[interrupted]" + Environment.NewLine + Environment.NewLine);
            StatusText.Text = "Generation stopped.";
        }
        catch (Exception ex)
        {
            ShowError(ex);
        }
        finally
        {
            _generationCts?.Dispose();
            _generationCts = null;
            SendButton.Content = "Send";
            await UpdateTokenStatsAsync();
        }

        if (!string.IsNullOrWhiteSpace(_pendingSteer))
        {
            var steer = _pendingSteer;
            _pendingSteer = null;
            await SendUserMessageAsync(steer);
        }
    }

    private GenerationOptions ReadGenerationOptions() =>
        new(
            ParseInt(MaxTokensBox.Text, 1024),
            ParseDouble(TemperatureBox.Text, 1.0),
            ParseDouble(TopPBox.Text, 0.95),
            ParseInt(TopKBox.Text, 64),
            ThinkingBox.IsChecked == true);

    private async Task UpdateTokenStatsAsync()
    {
        if (!_modelLoaded || _profile is null)
        {
            TokenStatsText.Text = "Tokens: model not loaded";
            return;
        }

        var messages = PromptBuilder.BuildMessages(BehaviourBox.Text, _conversation);
        var options = ReadGenerationOptions();
        var count = await _runtime.CountTokensAsync(messages, options, CancellationToken.None);
        TokenStatsText.Text = TokenUsage.Format(count, options.MaxTokens, _runtime.GetContextLimit()).Text;
    }

    private void RenderConversation()
    {
        ChatBox.Clear();
        foreach (var message in _conversation)
        {
            AppendChat($"{ToDisplayRole(message.Role)}: {message.Content}{Environment.NewLine}{Environment.NewLine}");
        }
    }

    private void AppendChat(string text)
    {
        ChatBox.AppendText(text);
        ChatBox.ScrollToEnd();
    }

    private void ShowError(Exception ex)
    {
        var formatted = DiagnosticsFormatter.FormatException(ex);
        DiagnosticsBox.AppendText(formatted + Environment.NewLine + Environment.NewLine);
        StatusText.Text = ex.Message;
        _profile?.AppendDiagnosticsAsync(formatted);
    }

    private static string ToDisplayRole(string role) =>
        role.Equals("assistant", StringComparison.OrdinalIgnoreCase) ? "Assistant" :
        role.Equals("system", StringComparison.OrdinalIgnoreCase) ? "System" : "You";

    private static int ParseInt(string raw, int fallback) =>
        int.TryParse(raw, out var value) ? value : fallback;

    private static double ParseDouble(string raw, double fallback) =>
        double.TryParse(raw, out var value) ? value : fallback;
}
