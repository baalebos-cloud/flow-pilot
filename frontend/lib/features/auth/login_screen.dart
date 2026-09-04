import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'auth_controller.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final controller = ref.read(authControllerProvider.notifier);
    final success = await controller.login(
      email: _emailController.text.trim(),
      password: _passwordController.text,
    );
    if (!mounted) return;
    if (success) {
      context.go('/wallet-setup');
    } else {
      final message = ref.read(authControllerProvider).errorMessage;
      BMoniToastOverlay.showError(context: context, message: message ?? 'Login failed');
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);

    return Scaffold(
      appBar: const CustomAppBar(title: 'Log in', showBackButton: false),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                HeadingText('Welcome back', level: 3, weight: HeadingWeight.semibold),
                const SizedBox(height: 8),
                BodyText(
                  'Log in to continue to FlowPilot.',
                  size: BodySize.medium,
                  weight: BodyWeight.regular,
                ),
                const SizedBox(height: 32),
                BMoniTextFormField.filled(
                  label: 'Email',
                  hintText: 'you@example.com',
                  controller: _emailController,
                  keyboardType: TextInputType.emailAddress,
                  validator: (value) =>
                      (value == null || !value.contains('@')) ? 'Enter a valid email' : null,
                ),
                const SizedBox(height: 16),
                BMoniTextFormField.filled(
                  label: 'Password',
                  hintText: 'Enter your password',
                  controller: _passwordController,
                  obscureText: true,
                  validator: (value) =>
                      (value == null || value.length < 8) ? 'Minimum 8 characters' : null,
                ),
                const SizedBox(height: 32),
                BMoniButton.primary(
                  onPressed: authState.isSubmitting ? null : _submit,
                  text: 'Log in',
                  isLoading: authState.isSubmitting,
                ),
                const SizedBox(height: 16),
                BMoniButton.ghost(
                  onPressed: authState.isSubmitting
                      ? null
                      : () => context.go('/register'),
                  text: "Don't have an account? Register",
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
