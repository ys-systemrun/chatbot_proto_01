import type { Meta, StoryObj } from '@storybook/react'
import Header from './Header'

const meta = {
  component: Header,
  title: 'Components/Header',
  args: {
    onChangeAskMode: () => {},
  },
} satisfies Meta<typeof Header>

export default meta
type Story = StoryObj<typeof meta>

export const Pipeline: Story = {
  args: {
    askMode: 'pipeline',
  },
}

export const Agentic: Story = {
  args: {
    askMode: 'agentic',
  },
}

export const Disabled: Story = {
  args: {
    askMode: 'agentic',
    disabled: true,
  },
}
