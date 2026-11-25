import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:myvoice_ai/core/constants/app_constants.dart';
import 'package:myvoice_ai/core/utils/script_detector.dart';
import 'package:myvoice_ai/data/models/generated_audio.dart';
import 'package:myvoice_ai/data/models/voice_profile.dart';
import 'package:myvoice_ai/data/providers/app_providers.dart';
import 'package:myvoice_ai/data/services/audio_player_service.dart';

class GenerateScreen extends ConsumerStatefulWidget {
  const GenerateScreen({super.key});

  @override
  ConsumerState<GenerateScreen> createState() => _GenerateScreenState();
}

class _GenerateScreenState extends ConsumerState<GenerateScreen> {
  final _textController = TextEditingController();
  String? _selectedProfileId;
  SpeakingStyle _style = SpeakingStyle.neutral;
  String _languageMode = 'auto';
  String _outputFormat = 'wav';
  double _speed = 1.0;
  double _exaggeration = 0.5;
  double _cfgWeight = 0.5;
  int _pauseMs = 110;
  bool _isGenerating = false;
  GeneratedAudio? _latestOutput;
  String? _errorText;

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  Future<bool> _ensureUploadConsent(String backendUrl) async {
    final config = ref.read(appStateProvider).backendConfig;
    if (config.uploadConsentRemembered) return true;

    var remember = false;
    final approved = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('Voice Upload Privacy Consent'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'MyVoice AI will send your selected voice sample and text to:\n$backendUrl\n\n'
                'Only proceed if you own this voice (or have explicit permission) and trust '
                'this backend endpoint.',
              ),
              const SizedBox(height: 12),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: remember,
                onChanged: (v) => setDialogState(() => remember = v ?? false),
                title: const Text('Remember my consent for this device'),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('I Consent & Generate'),
            ),
          ],
        ),
      ),
    );

    if (approved == true && remember) {
      await ref
          .read(appStateProvider.notifier)
          .saveBackendConfig(config.copyWith(uploadConsentRemembered: true));
    }
    return approved == true;
  }

  Future<void> _generate(List<VoiceProfile> profiles) async {
    final text = _textController.text.trim();
    if (text.isEmpty) {
      setState(() => _errorText = 'Please enter Bengali, English, or mixed text.');
      return;
    }
    if (profiles.isEmpty) {
      setState(() => _errorText = 'Create a Voice Profile first in the Profiles tab.');
      return;
    }

    final profile = profiles.firstWhere(
      (p) => p.id == _selectedProfileId,
      orElse: () => profiles.first,
    );

    final config = ref.read(appStateProvider).backendConfig;
    final consented = await _ensureUploadConsent(config.baseUrl);
    if (!consented) return;

    setState(() {
      _isGenerating = true;
      _errorText = null;
    });

    try {
      final result = await ref.read(appStateProvider.notifier).synthesizeAndSave(
            profile: profile,
            style: _style,
            text: text,
            languageMode: _languageMode,
            outputFormat: _outputFormat,
            speed: _speed,
            exaggeration: _exaggeration,
            cfgWeight: _cfgWeight,
            pauseMs: _pauseMs,
            consentConfirmed: true,
          );
      setState(() => _latestOutput = result);
    } catch (e) {
      setState(() => _errorText = e.toString());
    } finally {
      if (mounted) setState(() => _isGenerating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(appStateProvider);
    final player = ref.watch(audioPlayerProvider);
    final profiles = state.profiles;
    final detected = ScriptDetector.detect(_textController.text);
    final showStyleSliders = state.lastHealth?.activeEngine.supportsStyleControls ?? false;

    final selectedProfile = profiles.isEmpty
        ? null
        : profiles.firstWhere(
            (p) => p.id == _selectedProfileId,
            orElse: () => profiles.first,
          );

    return Scaffold(
      appBar: AppBar(title: const Text('MyVoice AI Studio')),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final isWide = constraints.maxWidth >= 780;
          final inputCard = _buildInputCard(
            context,
            profiles,
            selectedProfile,
            detected,
            showStyleSliders,
          );
          final outputCard = _buildOutputCard(context, player);

          if (isWide) {
            return Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 3, child: SingleChildScrollView(child: inputCard)),
                  const SizedBox(width: 16),
                  Expanded(flex: 2, child: SingleChildScrollView(child: outputCard)),
                ],
              ),
            );
          }

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              inputCard,
              const SizedBox(height: 16),
              outputCard,
            ],
          );
        },
      ),
    );
  }

  Widget _buildInputCard(
    BuildContext context,
    List<VoiceProfile> profiles,
    VoiceProfile? selectedProfile,
    DetectedScript detected,
    bool showStyleSliders,
  ) {
    final detectedLabel = switch (detected) {
      DetectedScript.bengali => 'Detected: Bengali',
      DetectedScript.english => 'Detected: English',
      DetectedScript.mixed => 'Detected: Mixed Bengali + English',
      DetectedScript.empty => 'Enter Bengali or English text',
    };

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            DropdownButtonFormField<String>(
              value: selectedProfile?.id,
              decoration: const InputDecoration(labelText: 'Voice Profile'),
              items: profiles
                  .map(
                    (p) => DropdownMenuItem(
                      value: p.id,
                      child: Text('${p.name} (${p.profileType.label})'),
                    ),
                  )
                  .toList(),
              onChanged: (val) => setState(() => _selectedProfileId = val),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _textController,
              maxLength: AppConstants.maxTextLength,
              maxLines: 5,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                labelText: 'Text to Speak (বাংলা / English / Mixed)',
                hintText: 'উদাহরণ: আজকে আমি MyVoice AI দিয়ে কথা বলছি।',
                alignLabelWithHint: true,
              ),
            ),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Chip(label: Text(detectedLabel)),
                DropdownButton<String>(
                  value: _languageMode,
                  items: const [
                    DropdownMenuItem(value: 'auto', child: Text('Lang: Auto')),
                    DropdownMenuItem(value: 'bn', child: Text('Lang: Bengali')),
                    DropdownMenuItem(value: 'en', child: Text('Lang: English')),
                    DropdownMenuItem(value: 'mixed', child: Text('Lang: Mixed Split')),
                  ],
                  onChanged: (v) {
                    if (v != null) setState(() => _languageMode = v);
                  },
                ),
                DropdownButton<SpeakingStyle>(
                  value: _style,
                  items: SpeakingStyle.values
                      .map((s) => DropdownMenuItem(value: s, child: Text('Style: ${s.label}')))
                      .toList(),
                  onChanged: (v) {
                    if (v != null) setState(() => _style = v);
                  },
                ),
                DropdownButton<String>(
                  value: _outputFormat,
                  items: const [
                    DropdownMenuItem(value: 'wav', child: Text('Format: WAV')),
                    DropdownMenuItem(value: 'mp3', child: Text('Format: MP3')),
                  ],
                  onChanged: (v) {
                    if (v != null) setState(() => _outputFormat = v);
                  },
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text('Speed: ${_speed.toStringAsFixed(2)}x'),
            Slider(
              value: _speed,
              min: 0.75,
              max: 1.35,
              divisions: 12,
              onChanged: (v) => setState(() => _speed = v),
            ),
            Text('Inter-segment Pause: $_pauseMs ms'),
            Slider(
              value: _pauseMs.toDouble(),
              min: 40,
              max: 300,
              divisions: 13,
              onChanged: (v) => setState(() => _pauseMs = v.round()),
            ),
            if (showStyleSliders) ...[
              Text('Expressiveness (Exaggeration): ${_exaggeration.toStringAsFixed(2)}'),
              Slider(
                value: _exaggeration,
                min: 0.25,
                max: 1.5,
                divisions: 25,
                onChanged: (v) => setState(() => _exaggeration = v),
              ),
              Text('Accent / CFG Adherence: ${_cfgWeight.toStringAsFixed(2)}'),
              Slider(
                value: _cfgWeight,
                min: 0.0,
                max: 1.0,
                divisions: 20,
                onChanged: (v) => setState(() => _cfgWeight = v),
              ),
            ],
            if (_errorText != null) ...[
              const SizedBox(height: 8),
              Text(
                _errorText!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _isGenerating ? null : () => _generate(profiles),
              icon: _isGenerating
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.graphic_eq),
              label: Text(_isGenerating ? 'Generating Speech...' : 'Generate Cloned Speech'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOutputCard(BuildContext context, AudioPlayerService player) {
    final output = _latestOutput;
    final activeEngineIsMock = ref.watch(appStateProvider).lastHealth?.activeEngine.isMock ?? false;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Generated Output', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            if (activeEngineIsMock && (output == null || !output.isMock))
              Container(
                padding: const EdgeInsets.all(10),
                margin: const EdgeInsets.only(bottom: 12),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.tertiaryContainer,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Text(
                  'Connected backend is using the Mock Pipeline Test Engine (synthetic tones only, not real AI voice cloning).',
                ),
              ),
            if (output == null)
              const Text(
                'Generated speech will appear here for instant playback and WAV/MP3 export.',
              )
            else ...[
              if (output.isMock)
                Container(
                  padding: const EdgeInsets.all(10),
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.tertiaryContainer,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Text(
                    'Mock Test Audio: Backend is running the offline mock engine (not real voice cloning).',
                  ),
                ),
              Text(output.text, maxLines: 3, overflow: TextOverflow.ellipsis),
              const SizedBox(height: 8),
              Text(
                '${output.profileName} • ${output.outputFormat.toUpperCase()} • '
                'Engine: ${output.engineId}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: FilledButton.tonalIcon(
                      onPressed: () => player.togglePlayFile(output.filePath),
                      icon: Icon(
                        player.activePath == output.filePath && player.isPlaying
                            ? Icons.pause
                            : Icons.play_arrow,
                      ),
                      label: Text(
                        player.activePath == output.filePath && player.isPlaying
                            ? 'Pause'
                            : 'Play',
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => ref.read(exportServiceProvider).shareOrSaveAudio(
                            filePath: output.filePath,
                            format: output.outputFormat,
                            label: output.profileName,
                          ),
                      icon: const Icon(Icons.download),
                      label: Text('Export ${output.outputFormat.toUpperCase()}'),
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
