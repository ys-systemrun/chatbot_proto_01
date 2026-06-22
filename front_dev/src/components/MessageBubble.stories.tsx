import type { Meta, StoryObj } from '@storybook/react'
import MessageBubble from './MessageBubble'

const meta = {
  component: MessageBubble,
  title: 'Components/MessageBubble',
} satisfies Meta<typeof MessageBubble>

export default meta
type Story = StoryObj<typeof meta>

export const User: Story = {
  args: {
    role: 'user',
    text: 'パスワードを忘れてしまいました。どうすればよいですか？',
  },
}

export const Assistant: Story = {
  args: {
    role: 'assistant',
    text: 'お問い合わせいただきありがとうございます。パスワードをリセットするには、ログイン画面の「パスワードを忘れた方はこちら」をクリックしてください。',
  },
}

export const AssistantWithRaw: Story = {
  args: {
    role: 'assistant',
    text: 'お問い合わせいただきありがとうございます。パスワードをリセットするには、ログイン画面の「パスワードを忘れた方はこちら」をクリックしてください。',
    rawResponse: {
      session_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      answer: 'お問い合わせいただきありがとうございます。パスワードをリセットするには、ログイン画面の「パスワードを忘れた方はこちら」をクリックしてください。',
    },
  },
}

export const Error: Story = {
  args: {
    role: 'error',
    text: 'HTTP 502 Bad Gateway: (no body)',
  },
}
