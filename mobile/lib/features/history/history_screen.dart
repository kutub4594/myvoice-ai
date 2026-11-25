import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:myvoice_ai/data/providers/app_providers.dart';

class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(appStateProvider).history;
    final player = ref.watch(audioPlayerProvider);
    final fmt = DateFormat('MMM d, h:mm a');

    return Scaffold(
      appBar: AppBar(title: const Text('Generation History')),
      body: history.isEmpty
          ? const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text('No generated speech clips yet.'),
              ),
            )
          : ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: history.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final item = history[index];
                final isThisPlaying = player.activePath == item.filePath && player.isPlaying;
                return Card(
                  child: ListTile(
                    leading: IconButton(
                      icon: Icon(isThisPlaying ? Icons.pause_circle : Icons.play_circle),
                      onPressed: () => player.togglePlayFile(item.filePath),
                    ),
                    title: Text(item.text, maxLines: 2, overflow: TextOverflow.ellipsis),
                    subtitle: Text(
                      '${item.profileName} • ${item.outputFormat.toUpperCase()} • '
                      '${item.engineId}${item.isMock ? ' (mock)' : ''} • '
                      '${fmt.format(item.createdAt)}',
                    ),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          tooltip: 'Export ${item.outputFormat.toUpperCase()}',
                          icon: const Icon(Icons.download_outlined),
                          onPressed: () => ref.read(exportServiceProvider).shareOrSaveAudio(
                                filePath: item.filePath,
                                format: item.outputFormat,
                                label: item.profileName,
                              ),
                        ),
                        IconButton(
                          tooltip: 'Delete',
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () async {
                            await player.stopIfActive(item.filePath);
                            await ref.read(appStateProvider.notifier).deleteGeneratedAudio(item);
                          },
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
