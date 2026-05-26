import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import * as crypto from 'crypto';

const OAUTH_STATE_TTL_MS = 10 * 60 * 1000;

@Injectable()
export class GithubOAuthService {
  constructor(private prisma: PrismaService) {}

  async createState(userId: string): Promise<string> {
    await this.prisma.oAuthState.deleteMany({
      where: {
        OR: [
          { userId },
          { expiresAt: { lt: new Date() } },
        ],
      },
    });

    const token = crypto.randomBytes(32).toString('hex');
    const expiresAt = new Date(Date.now() + OAUTH_STATE_TTL_MS);

    await this.prisma.oAuthState.create({
      data: {
        token,
        userId,
        expiresAt,
      },
    });

    return token;
  }

  async consumeState(token: string) {
    const oauthState = await this.prisma.oAuthState.findUnique({
      where: { token },
      include: { user: true },
    });

    if (!oauthState || oauthState.expiresAt < new Date()) {
      if (oauthState) {
        await this.prisma.oAuthState.delete({
          where: { id: oauthState.id },
        });
      }
      return null;
    }

    await this.prisma.oAuthState.delete({
      where: { id: oauthState.id },
    });

    return oauthState;
  }
}
