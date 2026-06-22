import type { Meta, StoryObj } from "@storybook/react";
import MessageBubble from "./MessageBubble";

const meta = {
  component: MessageBubble,
  title: "Stateless/MessageBubble",
} satisfies Meta<typeof MessageBubble>;

export default meta;
type Story = StoryObj<typeof meta>;

export const User: Story = {
  args: {
    role: "user",
    content: "パスワードを忘れてしまいました。どうすればよいですか？",
  },
};

export const Assistant: Story = {
  args: {
    role: "assistant",
    content:
      "お問い合わせいただきありがとうございます。パスワードをリセットするには、ログイン画面の「パスワードを忘れた方はこちら」をクリックしてください。",
  },
};

export const ErrorMessage: Story = {
  args: {
    role: "error",
    content: "HTTP 502 Bad Gateway: (no body)",
  },
};
