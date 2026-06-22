import type { Meta, StoryObj } from '@storybook/react'
import Header from './Header'

const meta = {
  component: Header,
  title: 'Components/Header',
  args: {
    onReset: () => {},
  },
} satisfies Meta<typeof Header>

export default meta
type Story = StoryObj<typeof meta>

export const NoSession: Story = {
  args: {
    sessionId: null,
  },
}

export const WithSession: Story = {
  args: {
    sessionId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
  },
}

export const Disabled: Story = {
  args: {
    sessionId: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    disabled: true,
  },
}
