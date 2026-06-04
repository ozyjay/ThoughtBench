using System.Text.Json;
using System.Text.RegularExpressions;
using Thoughtbench.Core.Profiles;

namespace Thoughtbench.Core.Knowledge;

public sealed partial class KnowledgeIndex
{
    public static readonly string[] SupportedSuffixes = [".md", ".txt"];

    private static readonly HashSet<string> StopWords = new(StringComparer.OrdinalIgnoreCase)
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from",
        "how", "i", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "what",
        "when", "where", "which", "with", "you"
    };

    private readonly List<string[]> _documentTokens;
    private readonly List<int> _documentLengths;
    private readonly Dictionary<string, double> _idf;
    private readonly double _averageDocumentLength;

    public IReadOnlyList<KnowledgeChunk> Chunks { get; }

    public IReadOnlyDictionary<string, FileSnapshot> Files { get; }

    public int ChunkSize { get; }

    public int ChunkOverlap { get; }

    public KnowledgeIndex(
        IReadOnlyList<KnowledgeChunk> chunks,
        IReadOnlyDictionary<string, FileSnapshot>? files = null,
        int chunkSize = 180,
        int chunkOverlap = 30)
    {
        Chunks = chunks;
        Files = files ?? new Dictionary<string, FileSnapshot>();
        ChunkSize = chunkSize;
        ChunkOverlap = chunkOverlap;
        _documentTokens = chunks.Select(chunk => Tokenize(chunk.Text).ToArray()).ToList();
        _documentLengths = _documentTokens.Select(tokens => tokens.Length).ToList();
        _averageDocumentLength = _documentLengths.Count == 0 ? 0 : _documentLengths.Average();
        _idf = BuildIdf();
    }

    public static KnowledgeIndex Empty() => new([]);

    public static KnowledgeIndex FromChunks(params (string ChunkId, string Source, string Text)[] chunks) =>
        new(chunks.Select(chunk => new KnowledgeChunk(chunk.ChunkId, chunk.Source, chunk.Text)).ToArray());

    public IReadOnlyList<KnowledgeResult> Retrieve(
        string query,
        int topK = 6,
        double minimumScore = 0.5,
        int minimumMatchedTerms = 1)
    {
        var terms = RetrievalTerms(query).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (terms.Length == 0 || Chunks.Count == 0)
        {
            return [];
        }

        var results = new List<KnowledgeResult>();
        for (var i = 0; i < Chunks.Count; i++)
        {
            var tokens = _documentTokens[i];
            var matched = terms.Where(term => tokens.Contains(term, StringComparer.OrdinalIgnoreCase)).ToArray();
            if (matched.Length < minimumMatchedTerms)
            {
                continue;
            }

            var score = Score(tokens, _documentLengths[i], terms);
            if (score >= minimumScore)
            {
                results.Add(new KnowledgeResult(Chunks[i], score, matched));
            }
        }

        return results
            .OrderByDescending(result => result.Score)
            .ThenBy(result => result.Chunk.Source, StringComparer.OrdinalIgnoreCase)
            .ThenBy(result => result.Chunk.ChunkId, StringComparer.OrdinalIgnoreCase)
            .Take(topK)
            .ToArray();
    }

    public static IReadOnlyList<KnowledgeChunk> ChunkText(
        string text,
        string source,
        int maxWords = 180,
        int overlapWords = 30)
    {
        var cleaned = NormaliseText(text);
        if (string.IsNullOrWhiteSpace(cleaned))
        {
            return [];
        }

        var paragraphs = Regex.Split(cleaned, @"\n\s*\n").Select(static part => part.Trim()).Where(static part => part.Length > 0);
        var chunks = new List<string>();
        var current = new List<string>();

        foreach (var paragraph in paragraphs)
        {
            var words = paragraph.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
            if (current.Count > 0 && current.Count + words.Length > maxWords)
            {
                chunks.Add(string.Join(' ', current).Trim());
                current = overlapWords > 0 ? current.TakeLast(overlapWords).ToList() : [];
            }

            if (words.Length > maxWords)
            {
                for (var start = 0; start < words.Length;)
                {
                    chunks.Add(string.Join(' ', words.Skip(start).Take(maxWords)).Trim());
                    if (start + maxWords >= words.Length)
                    {
                        break;
                    }

                    start += Math.Max(1, maxWords - overlapWords);
                }

                current.Clear();
            }
            else
            {
                current.AddRange(words);
            }
        }

        if (current.Count > 0)
        {
            chunks.Add(string.Join(' ', current).Trim());
        }

        return chunks
            .Where(static chunk => chunk.Length > 0)
            .Select((chunk, index) => new KnowledgeChunk($"{source}#{index + 1:0000}", source, chunk))
            .ToArray();
    }

    public static async Task<KnowledgeIndex> BuildAsync(
        string profileDirectory,
        KnowledgeSettings? settings = null,
        CancellationToken cancellationToken = default)
    {
        settings ??= KnowledgeSettings.Default;
        var knowledgeFolder = ProfilePaths.KnowledgeFolder(profileDirectory);
        Directory.CreateDirectory(knowledgeFolder);
        Directory.CreateDirectory(ProfilePaths.KnowledgeIndexFolder(profileDirectory));

        var chunks = new List<KnowledgeChunk>();
        var files = Snapshot(profileDirectory);
        foreach (var path in EnumerateKnowledgeFiles(profileDirectory))
        {
            var relative = Path.GetRelativePath(knowledgeFolder, path).Replace(Path.DirectorySeparatorChar, '/');
            var text = await File.ReadAllTextAsync(path, cancellationToken);
            chunks.AddRange(ChunkText(text, relative, settings.ChunkSize, settings.ChunkOverlap));
        }

        var index = new KnowledgeIndex(chunks, files, settings.ChunkSize, settings.ChunkOverlap);
        await SaveAsync(profileDirectory, index, cancellationToken);
        return index;
    }

    public static async Task SaveAsync(string profileDirectory, KnowledgeIndex index, CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(ProfilePaths.KnowledgeIndexFolder(profileDirectory));
        var dto = new KnowledgeIndexDto(
            index.Chunks.ToArray(),
            index.Files.ToDictionary(entry => entry.Key, entry => entry.Value),
            index.ChunkSize,
            index.ChunkOverlap);
        await File.WriteAllTextAsync(
            ProfilePaths.KnowledgeIndexPath(profileDirectory),
            JsonSerializer.Serialize(dto, JsonDefaults.Options),
            cancellationToken);
    }

    public static async Task<KnowledgeIndex> LoadAsync(string profileDirectory, CancellationToken cancellationToken = default)
    {
        var path = ProfilePaths.KnowledgeIndexPath(profileDirectory);
        if (!File.Exists(path))
        {
            return Empty();
        }

        try
        {
            var dto = JsonSerializer.Deserialize<KnowledgeIndexDto>(
                await File.ReadAllTextAsync(path, cancellationToken),
                JsonDefaults.Options);
            return dto is null ? Empty() : new KnowledgeIndex(dto.Chunks, dto.Files, dto.ChunkSize, dto.ChunkOverlap);
        }
        catch (JsonException)
        {
            return Empty();
        }
    }

    public static bool IsStale(string profileDirectory, KnowledgeIndex index, KnowledgeSettings? settings = null)
    {
        settings ??= KnowledgeSettings.Default;
        if (settings.ChunkSize != index.ChunkSize || settings.ChunkOverlap != index.ChunkOverlap)
        {
            return true;
        }

        var current = Snapshot(profileDirectory);
        return current.Count != index.Files.Count ||
               current.Any(entry =>
                   !index.Files.TryGetValue(entry.Key, out var existing) ||
                   existing.MtimeNs != entry.Value.MtimeNs ||
                   existing.Size != entry.Value.Size);
    }

    public static string FormatRetrievedContext(IReadOnlyList<KnowledgeResult> results, int maxChars = 6000)
    {
        if (results.Count == 0 || maxChars <= 0)
        {
            return string.Empty;
        }

        var parts = new List<string> { "Retrieved knowledge files:" };
        var length = parts[0].Length;
        foreach (var result in results)
        {
            var block = $"{Environment.NewLine}[{result.Chunk.ChunkId}] {result.Chunk.Text.Trim()}";
            if (length + block.Length > maxChars)
            {
                var remaining = maxChars - length;
                if (remaining > 20)
                {
                    parts.Add(block[..remaining].TrimEnd());
                }

                break;
            }

            parts.Add(block);
            length += block.Length;
        }

        return string.Join(string.Empty, parts).Trim();
    }

    public static async Task<KnowledgeSettings> LoadSettingsAsync(string profileDirectory, CancellationToken cancellationToken = default)
    {
        var path = ProfilePaths.KnowledgeSettingsPath(profileDirectory);
        if (!File.Exists(path))
        {
            return KnowledgeSettings.Default;
        }

        try
        {
            var settings = JsonSerializer.Deserialize<KnowledgeSettings>(
                await File.ReadAllTextAsync(path, cancellationToken),
                JsonDefaults.Options);
            return settings?.IsValid() == true ? settings : KnowledgeSettings.Default;
        }
        catch (JsonException)
        {
            return KnowledgeSettings.Default;
        }
    }

    public static Task SaveSettingsAsync(string profileDirectory, KnowledgeSettings settings, CancellationToken cancellationToken = default)
    {
        if (!settings.IsValid())
        {
            throw new ArgumentException("Knowledge settings are invalid.", nameof(settings));
        }

        return File.WriteAllTextAsync(
            ProfilePaths.KnowledgeSettingsPath(profileDirectory),
            JsonSerializer.Serialize(settings, JsonDefaults.Options),
            cancellationToken);
    }

    private Dictionary<string, double> BuildIdf()
    {
        if (_documentTokens.Count == 0)
        {
            return [];
        }

        var documentFrequency = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var token in _documentTokens.SelectMany(static tokens => tokens.Distinct(StringComparer.OrdinalIgnoreCase)))
        {
            documentFrequency[token] = documentFrequency.GetValueOrDefault(token) + 1;
        }

        return documentFrequency.ToDictionary(
            entry => entry.Key,
            entry => Math.Log(1 + ((_documentTokens.Count - entry.Value + 0.5) / (entry.Value + 0.5))),
            StringComparer.OrdinalIgnoreCase);
    }

    private double Score(IReadOnlyList<string> documentTokens, int documentLength, IReadOnlyList<string> queryTerms)
    {
        const double k1 = 1.5;
        const double b = 0.75;
        var counts = documentTokens.GroupBy(static token => token, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(static group => group.Key, static group => group.Count(), StringComparer.OrdinalIgnoreCase);
        var score = 0.0;
        foreach (var term in queryTerms)
        {
            if (!counts.TryGetValue(term, out var frequency))
            {
                continue;
            }

            var idf = _idf.GetValueOrDefault(term);
            var denominator = frequency + k1 * (1 - b + b * (documentLength / Math.Max(_averageDocumentLength, 1)));
            score += idf * ((frequency * (k1 + 1)) / denominator);
        }

        return score;
    }

    private static Dictionary<string, FileSnapshot> Snapshot(string profileDirectory)
    {
        var root = ProfilePaths.KnowledgeFolder(profileDirectory);
        return EnumerateKnowledgeFiles(profileDirectory).ToDictionary(
            path => Path.GetRelativePath(root, path).Replace(Path.DirectorySeparatorChar, '/'),
            path =>
            {
                var info = new FileInfo(path);
                return new FileSnapshot(info.LastWriteTimeUtc.Ticks * 100, info.Length);
            },
            StringComparer.OrdinalIgnoreCase);
    }

    private static IEnumerable<string> EnumerateKnowledgeFiles(string profileDirectory)
    {
        var root = ProfilePaths.KnowledgeFolder(profileDirectory);
        return Directory.Exists(root)
            ? Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories)
                .Where(path => SupportedSuffixes.Contains(Path.GetExtension(path), StringComparer.OrdinalIgnoreCase))
                .OrderBy(path => path, StringComparer.OrdinalIgnoreCase)
            : [];
    }

    private static IEnumerable<string> Tokenize(string text) =>
        TokenRegex().Matches(text.ToLowerInvariant()).Select(match => match.Value);

    private static IEnumerable<string> RetrievalTerms(string text) =>
        Tokenize(text).Where(token => !StopWords.Contains(token));

    private static string NormaliseText(string text) =>
        string.Join('\n', text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n').Select(static line => line.TrimEnd())).Trim();

    [GeneratedRegex(@"[A-Za-z0-9_./\\:-]+")]
    private static partial Regex TokenRegex();
}

public sealed record FileSnapshot(long MtimeNs, long Size);

internal sealed record KnowledgeIndexDto(
    KnowledgeChunk[] Chunks,
    Dictionary<string, FileSnapshot> Files,
    int ChunkSize,
    int ChunkOverlap);
