import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { User, Prisma } from '@prisma/client';

@Injectable()
export class UsersService {
  constructor(private prisma: PrismaService) {}

  async findOrCreate(data: { telegramId: string; username?: string; firstName?: string; lastName?: string }): Promise<User> {
    const user = await this.prisma.user.findUnique({
      where: { telegramId: data.telegramId },
    });

    if (user) {
      // Update info if it changed
      return this.prisma.user.update({
        where: { id: user.id },
        data: {
          username: data.username,
          firstName: data.firstName,
          lastName: data.lastName,
        },
      });
    }

    return this.prisma.user.create({
      data,
    });
  }

  async findByTelegramId(telegramId: string): Promise<User | null> {
    return this.prisma.user.findUnique({
      where: { telegramId },
    });
  }

  async findByApiToken(apiToken: string): Promise<User | null> {
    return this.prisma.user.findUnique({
      where: { apiToken },
    });
  }

  async findById(id: string): Promise<User | null> {
    return this.prisma.user.findUnique({
      where: { id },
    });
  }

  async updateGithubConnection(userId: string, githubToken: string, githubLogin: string): Promise<User> {
    return this.prisma.user.update({
      where: { id: userId },
      data: {
        githubToken,
        githubLogin,
      },
    });
  }

  async updateGeminiApiKey(userId: string, geminiApiKey: string): Promise<User> {
    return this.prisma.user.update({
      where: { id: userId },
      data: { geminiApiKey },
    });
  }
}

