	.section	__TEXT,__text,regular,pure_instructions
	.globl	_Z3foov
_Z3foov:
	pushq	%rbp
	movq	%rsp, %rbp
	vmovups	(%rdi), %xmm0
	movaps	16(%rdi), %xmm1
	popq	%rbp
	retq
