import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:myvoice_ai/core/constants/app_constants.dart';
import 'package:myvoice_ai/data/models/backend_health.dart';
import 'package:myvoice_ai/data/providers/app_providers.dart';

class BackendSettingsScreen extends ConsumerStatefulWidget {
  const BackendSettingsScreen({super.key});

  @override
  ConsumerState<BackendSettingsScreen> createState() => _BackendSettingsScreenState();
}

class _BackendSettingsScreenState extends ConsumerState<BackendSettingsScreen> {
  late final TextEditingController _urlController;
  bool _checking = false;
  String? _statusMessage;
  bool _hasError = false;

  @override
  void initState() {
    super.initState();
    final config = ref.read(appStateProvider).backendConfig;
    _urlController = TextEditingController(text: config.baseUrl);
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _saveAndTest() async {
    final notifier = ref.read(appStateProvider.notifier);
    final current = ref.read(appStateProvider).backendConfig;
    await notifier.saveBackendConfig(
      current.copyWith(baseUrl: _urlController.text.trim()),
    );

    setState(() {
      _checking = true;
      _statusMessage = null;
      _hasError = false;
    });

    try {
      final health = await notifier.testBackendHealth();
      setState(() {
        final mockNotice = health.activeEngine.isMock
            ? ' [MOCK TEST ENGINE — synthetic tone only, NOT real voice cloning]'
            : '';
        _statusMessage =
            'Connected (${health.status.toUpperCase()}): ${health.activeEngine.name} '
            '[status=${health.activeEngine.status}]$mockNotice';
        _hasError = false;
      });
    } catch (e) {
      setState(() {
        _statusMessage = e.toString();
        _hasError = true;
      });
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _confirmWipeAll() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete All Voice Data?'),
        content: const Text(
          'This permanently deletes all saved voice profiles, dataset recordings, and '
          'generated audio files from this phone.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete Everything'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await ref.read(audioPlayerProvider).stop();
      await ref.read(appStateProvider.notifier).wipeAllPrivateData();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('All local voice data permanently deleted.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(appStateProvider);
    final BackendHealth? health = state.lastHealth;

    return Scaffold(
      appBar: AppBar(title: const Text('Backend & Privacy Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Backend Server URL', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _urlController,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: 'FastAPI / Tunnel Base URL',
                      hintText: 'https://your-colab-tunnel.trycloudflare.com',
                    ),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: AppConstants.backendPresets
                        .map(
                          (preset) => ActionChip(
                            label: Text(preset['label']!),
                            onPressed: () => _urlController.text = preset['url']!,
                          ),
                        )
                        .toList(),
                  ),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _checking ? null : _saveAndTest,
                    icon: _checking
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.health_and_safety_outlined),
                    label: Text(_checking ? 'Checking /health...' : 'Save & Test Connection'),
                  ),
                  if (_statusMessage != null) ...[
                    const SizedBox(height: 10),
                    Text(
                      _statusMessage!,
                      style: TextStyle(
                        color: _hasError
                            ? Theme.of(context).colorScheme.error
                            : Theme.of(context).colorScheme.primary,
                      ),
                    ),
                  ],
                  if (health != null) ...[
                    const Divider(height: 24),
                    Text('Engine ID: ${health.activeEngine.id}'),
                    Text('FFmpeg Ready: ${health.ffmpegAvailable ? 'Yes' : 'No'}'),
                    Text('Privacy Mode: ${health.privacyMode}'),
                    if (health.activeEngine.licenses.isNotEmpty)
                      Text('Licenses: ${health.activeEngine.licenses.join(' | ')}'),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Privacy & Data Controls', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    value: state.backendConfig.uploadConsentRemembered,
                    onChanged: (val) => ref.read(appStateProvider.notifier).saveBackendConfig(
                          state.backendConfig.copyWith(uploadConsentRemembered: val),
                        ),
                    title: const Text('Remember Upload Consent'),
                    subtitle: const Text(
                      'When off, the app asks for confirmation before every voice sample upload.',
                    ),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: _confirmWipeAll,
                    icon: const Icon(Icons.delete_forever_outlined),
                    label: const Text('Permanently Delete All Local Voice Data'),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
