import { Test, TestingModule } from '@nestjs/testing';
import { UsersService } from './users.service';
import { PrismaService } from '../prisma/prisma.service';

describe('UsersService', () => {
  let service: UsersService;
  let prisma: PrismaService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        UsersService,
        {
          provide: PrismaService,
          useValue: {
            user: {
              findUnique: jest.fn(),
              create: jest.fn(),
              update: jest.fn(),
            },
          },
        },
      ],
    }).compile();

    service = module.get<UsersService>(UsersService);
    prisma = module.get<PrismaService>(PrismaService);
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  it('should find or create a user', async () => {
    const mockUser = { id: '1', telegramId: '123', createdAt: new Date(), updatedAt: new Date(), username: null, firstName: null, lastName: null };
    (prisma.user.findUnique as jest.Mock).mockResolvedValue(null);
    (prisma.user.create as jest.Mock).mockResolvedValue(mockUser);

    const result = await service.findOrCreate({ telegramId: '123' });
    expect(result).toEqual(mockUser);
    expect(prisma.user.create).toHaveBeenCalledWith({ data: { telegramId: '123' } });
  });

  it('should update the GitHub connection for a user', async () => {
    const mockUser = {
      id: '1',
      telegramId: '123',
      githubToken: 'token',
      githubLogin: 'octocat',
    };
    (prisma.user.update as jest.Mock).mockResolvedValue(mockUser);

    const result = await service.updateGithubConnection('1', 'token', 'octocat');

    expect(result).toEqual(mockUser);
    expect(prisma.user.update).toHaveBeenCalledWith({
      where: { id: '1' },
      data: {
        githubToken: 'token',
        githubLogin: 'octocat',
      },
    });
  });
});
