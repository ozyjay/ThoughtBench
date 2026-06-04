using Thoughtbench.Core.Chat;
using Thoughtbench.Core.Modeling;
using Thoughtbench.Core.Profiles;
using Thoughtbench.Onnx;

namespace Thoughtbench.Cli;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        if (args.Length == 0 || args[0] is "-h" or "--help")
        {
            PrintHelp();
            return 0;
        }

        return args[0].ToLowerInvariant() switch
        {
            "generate" => await GenerateAsync(args[1..]),
            "chat" => await ChatAsync(args[1..]),
            _ => UnknownCommand(args[0])
        };
    }

    private static async Task<int> GenerateAsync(string[] args)
    {
        var options = CliOptions.Parse(args);
        if (string.IsNullOrWhiteSpace(options.Prompt))
        {
            Console.Error.WriteLine("Missing prompt. Usage: thoughtbench generate \"your prompt\" --model-path D:\\LLMProjects\\HuggingFace\\Hub\\local\\Thoughtbench\\onnx");
            return 2;
        }

        using var runtime = new OnnxModelRuntime();
        await runtime.LoadAsync(new ModelSelection("CLI ONNX model", options.ModelPath), CancellationToken.None);
        var messages = PromptBuilder.BuildMessages(options.SystemPrompt, [], options.Prompt);
        var progress = new Progress<GenerationChunk>(chunk =>
        {
            if (chunk.Channel == GenerationChannel.Response)
            {
                Console.Write(chunk.Text);
            }
        });
        await runtime.GenerateAsync(messages, options.ToGenerationOptions(), progress, CancellationToken.None);
        Console.WriteLine();
        return 0;
    }

    private static async Task<int> ChatAsync(string[] args)
    {
        var options = CliOptions.Parse(args);
        using var runtime = new OnnxModelRuntime();
        await runtime.LoadAsync(new ModelSelection("CLI ONNX model", options.ModelPath), CancellationToken.None);
        var messages = new List<ChatMessage> { new("system", options.SystemPrompt) };
        var thinking = options.Think;

        Console.WriteLine("Type your message. Commands: /think, /reset, /behaviour <instruction>, Ctrl+C to exit.");
        Console.WriteLine($"Thinking mode: {(thinking ? "ON" : "OFF")}");

        while (true)
        {
            Console.Write("You: ");
            var input = Console.ReadLine();
            if (input is null)
            {
                return 0;
            }

            input = input.Trim();
            if (input.Length == 0)
            {
                continue;
            }

            if (input.Equals("/think", StringComparison.OrdinalIgnoreCase))
            {
                thinking = !thinking;
                Console.WriteLine($"Thinking mode: {(thinking ? "ON" : "OFF")}");
                continue;
            }

            if (input.Equals("/reset", StringComparison.OrdinalIgnoreCase))
            {
                messages = [new ChatMessage("system", options.SystemPrompt)];
                Console.WriteLine("Conversation reset.");
                continue;
            }

            if (input.StartsWith("/behaviour ", StringComparison.OrdinalIgnoreCase))
            {
                options.SystemPrompt = $"{options.SystemPrompt}{Environment.NewLine}- {input["/behaviour ".Length..].Trim()}".Trim();
                messages[0] = new ChatMessage("system", options.SystemPrompt);
                Console.WriteLine("Assistant behaviour updated.");
                continue;
            }

            messages.Add(new ChatMessage("user", input));
            var responseText = string.Empty;
            var progress = new Progress<GenerationChunk>(chunk =>
            {
                if (chunk.Channel == GenerationChannel.Response)
                {
                    Console.Write(chunk.Text);
                    responseText += chunk.Text;
                }
            });

            Console.Write("Assistant: ");
            var response = await runtime.GenerateAsync(
                messages,
                options.ToGenerationOptions() with { ThinkingEnabled = thinking },
                progress,
                CancellationToken.None);
            Console.WriteLine();
            messages.Add(new ChatMessage("assistant", string.IsNullOrWhiteSpace(response) ? responseText.Trim() : response));
        }
    }

    private static int UnknownCommand(string command)
    {
        Console.Error.WriteLine($"Unknown command: {command}");
        PrintHelp();
        return 2;
    }

    private static void PrintHelp()
    {
        Console.WriteLine(
            """
            Thoughtbench C# CLI

            Usage:
              thoughtbench generate "prompt" --model-path D:\LLMProjects\HuggingFace\Hub\local\Thoughtbench\onnx
              thoughtbench chat --model-path D:\LLMProjects\HuggingFace\Hub\local\Thoughtbench\onnx

            Options:
              --model-path <path>   Required ONNX GenAI model folder.
              --system <text>       System prompt. Defaults to "You are a helpful assistant."
              --think               Enable thinking mode when the model/template supports it.
              --max-tokens <n>      Max new tokens. Default 2048.
              --temperature <n>     Sampling temperature. Default 1.0.
              --top-p <n>           Top-p sampling. Default 0.95.
              --top-k <n>           Top-k sampling. Default 64.
            """);
    }
}

internal sealed class CliOptions
{
    public string ModelPath { get; private set; } = Environment.GetEnvironmentVariable("THOUGHTBENCH_ONNX_MODEL") ?? string.Empty;
    public string SystemPrompt { get; set; } = "You are a helpful assistant.";
    public string? Prompt { get; private set; }
    public bool Think { get; private set; }
    public int MaxTokens { get; private set; } = 2048;
    public double Temperature { get; private set; } = 1.0;
    public double TopP { get; private set; } = 0.95;
    public int TopK { get; private set; } = 64;

    public static CliOptions Parse(string[] args)
    {
        var options = new CliOptions();
        for (var i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--model-path" when i + 1 < args.Length:
                    options.ModelPath = args[++i];
                    break;
                case "--system" when i + 1 < args.Length:
                    options.SystemPrompt = args[++i];
                    break;
                case "--think":
                    options.Think = true;
                    break;
                case "--max-tokens" when i + 1 < args.Length && int.TryParse(args[i + 1], out var maxTokens):
                    options.MaxTokens = maxTokens;
                    i++;
                    break;
                case "--temperature" when i + 1 < args.Length && double.TryParse(args[i + 1], out var temperature):
                    options.Temperature = temperature;
                    i++;
                    break;
                case "--top-p" when i + 1 < args.Length && double.TryParse(args[i + 1], out var topP):
                    options.TopP = topP;
                    i++;
                    break;
                case "--top-k" when i + 1 < args.Length && int.TryParse(args[i + 1], out var topK):
                    options.TopK = topK;
                    i++;
                    break;
                default:
                    options.Prompt ??= args[i];
                    break;
            }
        }

        if (string.IsNullOrWhiteSpace(options.ModelPath))
        {
            throw new ArgumentException("Provide --model-path or set THOUGHTBENCH_ONNX_MODEL.");
        }

        return options;
    }

    public GenerationOptions ToGenerationOptions() =>
        new(MaxTokens, Temperature, TopP, TopK, Think);
}
