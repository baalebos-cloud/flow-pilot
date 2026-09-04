import 'package:bkey_uikit/bkey_uikit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'auth_controller.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    final controller = ref.read(authControllerProvider.notifier);
    final success = await controller.register(
      email: _emailController.text.trim(),
      name: _nameController.text.trim(),
      password: _passwordController.text,
    );
    if (!mounted) return;
    if (success) {
      context.go('/wallet-setup');
    } else {
      final message = ref.read(authControllerProvider).errorMessage;
      BMoniToastOverlay.showError(context: context, message: message ?? 'Registration failed');
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);

    return Scaffold(
      appBar: const CustomAppBar(title: 'Create account', showBackButton: false),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                HeadingText('Get started', level: 3, weight: HeadingWeight.semibold),
                const SizedBox(height: 8),
                BodyText(
                  'Create a FlowPilot demo account.',
                  size: BodySize.medium,
                  weight: BodyWeight.regular,
                ),
                const SizedBox(height: 32),
                BMoniTextFormField.filled(
                  label: 'Full name',
                  hintText: 'Demo User',
                  controller: _nameController,
                  validator: (value) =>
                      (value == null || value.trim().length < 2) ? 'Enter your name' : null,
                ),
                const SizedBox(height: 16),
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
                  hintText: 'At least 8 characters',
                  controller: _passwordController,
                  obscureText: true,
                  validator: (value) =>
                      (value == null || value.length < 8) ? 'Minimum 8 characters' : null,
                ),
                const SizedBox(height: 32),
                BMoniButton.primary(
                  onPressed: authState.isSubmitting ? null : _submit,
                  text: 'Create account',
                  isLoading: authState.isSubmitting,
                ),
                const SizedBox(height: 16),
                BMoniButton.ghost(
                  onPressed: authState.isSubmitting ? null : () => context.go('/login'),
                  text: 'Already have an account? Log in',
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
