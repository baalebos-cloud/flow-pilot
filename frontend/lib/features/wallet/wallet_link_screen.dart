import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../core/widgets/mock_mode_banner.dart';
import 'wallet_repository.dart';

final walletRepositoryProvider = Provider<WalletRepository>((ref) => WalletRepository());

class WalletLinkScreen extends ConsumerStatefulWidget {
  const WalletLinkScreen({super.key});

  @override
  ConsumerState<WalletLinkScreen> createState() => _WalletLinkScreenState();
}

class _WalletLinkScreenState extends ConsumerState<WalletLinkScreen> {
  // The real BMONI SDK acquisition/signing contract isn't confirmed yet
  // (see handoff doc, "known backend gaps"), so we fall back to a clearly
  // labelled mock public address for the demo.
  final _addressController = TextEditingController(text: '0xMOCKDEMOWALLETADDRESS0001');
  bool _isSubmitting = false;

  @override
  void dispose() {
    _addressController.dispose();
    super.dispose();
  }

  Future<void> _linkWallet() async {
    setState(() => _isSubmitting = true);
    try {
      await ref.read(walletRepositoryProvider).linkWallet(
            walletAddress: _addressController.text.trim(),
          );
      if (!mounted) return;
      BMoniToastOverlay.showSuccess(context: context, message: 'Wallet linked');
      context.go('/pockets');
    } on ApiException catch (e) {
      if (!mounted) return;
      BMoniToastOverlay.showError(context: context, message: e.message);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const CustomAppBar(title: 'Link wallet', showBackButton: false),
      body: SafeArea(
        child: Column(
          children: [
            const MockModeBanner(),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    HeadingText('Link your wallet', level: 3, weight: HeadingWeight.semibold),
                    const SizedBox(height: 8),
                    BodyText(
                      'Only a public wallet address is ever sent to FlowPilot. '
                      'Private keys and signing PINs never leave your device.',
                      size: BodySize.medium,
                      weight: BodyWeight.regular,
                    ),
                    const SizedBox(height: 24),
                    InfoCard(
                      title: 'Using a mock address',
                      message: 'The live BMONI SDK isn\'t wired up yet, so this demo uses a '
                          'clearly labelled mock public address.',
                      icon: Icons.info_outline,
                    ),
                    const SizedBox(height: 24),
                    BMoniTextFormField.filled(
                      label: 'Public wallet address',
                      hintText: '0x...',
                      controller: _addressController,
                    ),
                    const SizedBox(height: 32),
                    BMoniButton.primary(
                      onPressed: _isSubmitting ? null : _linkWallet,
                      text: 'Link wallet',
                      isLoading: _isSubmitting,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
