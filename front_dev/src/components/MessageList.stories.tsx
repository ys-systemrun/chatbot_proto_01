import type { Meta, StoryObj } from '@storybook/react'
import MessageList from './MessageList'

const meta = {
  component: MessageList,
  title: 'Components/MessageList',
} satisfies Meta<typeof MessageList>

export default meta
type Story = StoryObj<typeof meta>

export const Empty: Story = {
  args: { messages: [] },
}

export const Conversation: Story = {
  args: {
    messages: [
      { id: 1, role: 'user', text: 'パスワードを忘れました' },
      {
        id: 2,
        role: 'assistant',
        text: 'お問い合わせいただきありがとうございます。ログイン画面の「パスワードを忘れた方はこちら」をご利用ください。',
        rawResponse: {
          session_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
          answer: 'お問い合わせいただきありがとうございます。ログイン画面の「パスワードを忘れた方はこちら」をご利用ください。',
        },
      },
      { id: 3, role: 'user', text: 'ありがとうございます。試してみます。' },
    ],
  },
}

export const WithError: Story = {
  args: {
    messages: [
      { id: 1, role: 'user', text: 'テスト' },
      { id: 2, role: 'error', text: 'HTTP 502 Bad Gateway: (no body)' },
    ],
  },
}

export const Loading: Story = {
  args: {
    messages: [{ id: 1, role: 'user', text: 'パスワードを忘れました' }],
    isLoading: true,
  },
}
