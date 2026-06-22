import type { Meta, StoryObj } from "@storybook/react";
import MessageList from "./MessageList";

const meta = {
  component: MessageList,
  title: "Stateless/MessageList",
} satisfies Meta<typeof MessageList>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {
  args: { messages: [] },
};

export const Conversation: Story = {
  args: {
    messages: [
      { order: 1, role: "user",      content: "パスワードを忘れました" },
      { order: 2, role: "assistant", content: "お問い合わせいただきありがとうございます。ログイン画面の「パスワードを忘れた方はこちら」をご利用ください。" },
      { order: 3, role: "user",      content: "ありがとうございます。試してみます。" },
    ],
  },
};

export const WithError: Story = {
  args: {
    messages: [
      { order: 1, role: "user",  content: "テスト" },
      { order: 2, role: "error", content: "HTTP 502 Bad Gateway: (no body)" },
    ],
  },
};

export const Loading: Story = {
  args: {
    messages: [
      { order: 1, role: "user", content: "パスワードを忘れました" },
    ],
    isLoading: true,
  },
};
